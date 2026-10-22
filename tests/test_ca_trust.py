"""Trust checks exercise real PEM parsing, bootstrap wheels and TLS choices."""

import importlib.util
import subprocess
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import certifi
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

SPEC = importlib.util.spec_from_file_location(
    "ca_trust", Path(__file__).resolve().parents[1] / "tools/check_ca_trust.py"
)
assert SPEC and SPEC.loader
trust = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trust)


def certificate(common_name):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )


@pytest.mark.parametrize("name", sorted(trust.DISTRUSTED_ROOTS))
def test_rejects_each_disclosed_root_and_cross_sign(name):
    with pytest.raises(ValueError, match="distrusted CA roots"):
        trust.check_bundle(
            certificate("Unaffected test CA") + certificate(name), "fixture"
        )


def test_parses_certificates_not_pem_comments():
    data = b"# emSign ECC Root CA - G3 was removed\n" + certificate(
        "Unaffected test CA"
    )
    assert trust.check_bundle(data, "fixture")["ca_count"] == 1


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not a bundle",
        b"-----BEGIN CERTIFICATE-----\nbroken\n-----END CERTIFICATE-----",
    ],
)
def test_empty_and_malformed_bundles_fail_closed(data):
    with pytest.raises(ValueError, match="invalid or empty"):
        trust.check_bundle(data, "fixture")


def test_checks_embedded_ensurepip_wheels(tmp_path, monkeypatch):
    monkeypatch.setattr(trust, "installed_bundles", lambda *args: [])
    monkeypatch.setattr(trust.sysconfig, "get_path", lambda _: str(tmp_path))
    monkeypatch.setattr(trust.importlib.metadata, "version", lambda _: "9999.0.0")
    bundled = tmp_path / "ensurepip/_bundled"
    bundled.mkdir(parents=True)
    with zipfile.ZipFile(bundled / "pip-test.whl", "w") as archive:
        archive.writestr(
            "pip/_vendor/certifi/cacert.pem", certificate("emSign ECC Root CA - G3")
        )
    with pytest.raises(ValueError, match="ensurepip/pip-test.whl: distrusted"):
        trust.check_environment()


def test_current_runtime_bundles_are_checked():
    result = trust.check_environment(runtime=True)
    assert {b["bundle"] for b in result["bundles"]} >= {"certifi", "grpc"}
    assert result["passed"]


def test_cli_runs_without_optional_sdk_imports():
    result = subprocess.run(
        [sys.executable, str(SPEC.origin), "--runtime"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("verify", [True, False, "custom-ca.pem"])
def test_pipeline_s3_uses_maintained_ca_and_preserves_explicit_options(
    monkeypatch, verify
):
    import boto3
    from dockflow_pipelines.artifacts import ArtifactStore

    captured = {}
    monkeypatch.setattr(
        boto3, "client", lambda *a, **kw: captured.update(kw) or object()
    )
    store = object.__new__(ArtifactStore)
    store._client = None
    store.options = {"endpoint": "https://objects.invalid", "tls_verify": verify}
    store._s3()
    assert captured["verify"] == (certifi.where() if verify is True else verify)


@pytest.mark.parametrize("verify", ["omitted", None, True, False, "custom-ca.pem"])
def test_artifact_s3_uses_maintained_ca_and_preserves_explicit_options(
    monkeypatch, verify
):
    import boto3
    from dockflow_artifacts._storage import S3Store

    captured = {}
    monkeypatch.delenv("AWS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", "/nonexistent-dockflow-test-config")
    monkeypatch.setattr(
        boto3, "client", lambda *a, **kw: captured.update(kw) or object()
    )
    options = {} if verify == "omitted" else {"verify": verify}
    assert S3Store("s3://bucket/prefix", options).client is not None
    assert captured["verify"] == (
        certifi.where()
        if verify == "omitted" or verify is None or verify is True
        else verify
    )
    assert options == ({} if verify == "omitted" else {"verify": verify})


def test_artifact_s3_retains_explicit_environment_bundle(monkeypatch):
    import boto3
    from dockflow_artifacts._storage import S3Store

    captured = {}
    monkeypatch.setenv("AWS_CA_BUNDLE", "organization-ca.pem")
    monkeypatch.setattr(
        boto3, "client", lambda *a, **kw: captured.update(kw) or object()
    )
    assert S3Store("s3://bucket/prefix", {}).client is not None
    assert captured["verify"] == "organization-ca.pem"


def test_artifact_s3_retains_profile_ca_bundle(tmp_path, monkeypatch):
    import boto3
    from dockflow_artifacts._storage import S3Store

    captured = {}
    config = tmp_path / "config"
    config.write_text("[default]\nca_bundle = profile-ca.pem\n")
    monkeypatch.delenv("AWS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setattr(
        boto3, "client", lambda *a, **kw: captured.update(kw) or object()
    )
    assert S3Store("s3://bucket/prefix", {}).client is not None
    assert captured["verify"] == "profile-ca.pem"
