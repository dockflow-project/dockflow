#!/usr/bin/env python3
"""Reject certificate bundles affected by the October 2026 emSign incident.

This is an offline build/installation check, not a replacement TLS verifier.
Upstream root-removal guidance: https://www.openwall.com/lists/oss-security/2026/10/20/1
"""

import argparse
import importlib.metadata
import importlib.util
import json
import ssl
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

# Check all three trust paths, including the cross-sign through AAA. Match parsed
# certificate subjects, not comments or textual labels in a PEM file.
DISTRUSTED_ROOTS = frozenset(
    {"emSign ECC Root CA - G3", "emSign Root TLS CA - G3", "AAA Certificate Services"}
)
MINIMUM_VERSIONS = {
    "certifi": (2026, 10, 19),
    "grpcio": (1, 84, 1),
    "pip": (26, 2, 2),
    "sigstore": (4, 5, 1),
}


def check_bundle(data: bytes, label: str) -> dict:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        context.load_verify_locations(cadata=data.decode("ascii"))
    except (ValueError, UnicodeError, ssl.SSLError) as exc:
        raise ValueError(f"{label}: invalid or empty certificate bundle") from exc
    certificates = context.get_ca_certs()
    if not certificates:
        raise ValueError(f"{label}: certificate bundle has no CA certificates")
    names = {
        value
        for cert in certificates
        for rdn in cert["subject"]
        for key, value in rdn
        if key == "commonName"
    }
    affected = names & DISTRUSTED_ROOTS
    if affected:
        raise ValueError(f"{label}: distrusted CA roots: {', '.join(sorted(affected))}")
    return {"bundle": label, "ca_count": len(certificates)}


def installed_bundles(runtime: bool, all_bundles: bool):
    for module, relative in (
        ("certifi", "cacert.pem"),
        ("grpc", "_cython/_credentials/roots.pem"),
        ("pip", "_vendor/certifi/cacert.pem"),
    ):
        spec = importlib.util.find_spec(module)
        if spec and spec.origin:
            yield module, Path(spec.origin).parent / relative
        elif runtime and module != "pip":
            raise ValueError(f"{module}: required runtime certificate bundle missing")
    if all_bundles:
        spec = importlib.util.find_spec("botocore")
        if spec and spec.origin:
            yield "botocore vendored", Path(spec.origin).parent / "cacert.pem"
    # A venv hides base-interpreter site-packages, but they ship in the image.
    base = Path(sys.base_prefix)
    for folder in (
        base / "Lib/site-packages",
        base
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages",
    ):
        bundle = folder / "pip/_vendor/certifi/cacert.pem"
        if bundle.is_file():
            yield "base interpreter pip", bundle


def check_environment(
    *, runtime: bool = False, system: bool = False, all_bundles: bool = False
) -> dict:
    bundles, versions = [], {}
    for name, minimum in MINIMUM_VERSIONS.items():
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        versions[name] = version
        try:
            parsed = tuple(int(part) for part in version.split("."))
        except ValueError as exc:
            raise ValueError(f"{name}: unqualified version {version}") from exc
        if parsed < minimum:
            raise ValueError(f"{name}: {version} is below the incident security floor")
    for label, path in installed_bundles(runtime, all_bundles):
        if not path.is_file():
            raise ValueError(f"{label}: certificate bundle missing")
        bundles.append(check_bundle(path.read_bytes(), label))
    # ensurepip seeds new environments from wheels, not the installed pip.
    bundled = Path(sysconfig.get_path("stdlib")) / "ensurepip/_bundled"
    for wheel in sorted(bundled.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            members = [
                n for n in archive.namelist() if n.endswith("/certifi/cacert.pem")
            ]
            if not members:
                raise ValueError(f"ensurepip/{wheel.name}: certificate bundle missing")
            for member in members:
                bundles.append(
                    check_bundle(archive.read(member), f"ensurepip/{wheel.name}")
                )
    if system:
        # Explicit Linux image check. OS stores on other platforms can enforce
        # intermediate revocation independently; this does not audit that policy.
        bundle = Path("/etc/ssl/certs/ca-certificates.crt")
        if not bundle.is_file():
            raise ValueError("system: expected Linux CA bundle missing")
        bundles.append(check_bundle(bundle.read_bytes(), "system"))
    if not bundles:
        raise ValueError("No certificate bundles were inspected")
    return {
        "passed": True,
        "python": sys.version.split()[0],
        "versions": versions,
        "bundles": bundles,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime", action="store_true", help="Require all service runtime bundles"
    )
    parser.add_argument(
        "--system", action="store_true", help="Also inspect the Linux system CA bundle"
    )
    parser.add_argument(
        "--image",
        help="Inspect this local Docker service image without network or mounts",
    )
    parser.add_argument(
        "--all-bundles",
        action="store_true",
        help="Include dormant SDK bundles in images",
    )
    parser.add_argument(
        "--system-image",
        help="Inspect the Linux CA bundle in a non-Python Docker image",
    )
    args = parser.parse_args()
    if args.system_image:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--entrypoint",
                "cat",
                args.system_image,
                "/etc/ssl/certs/ca-certificates.crt",
            ],
            capture_output=True,
            check=True,
        )
        print(json.dumps(check_bundle(result.stdout, "image system"), indent=2))
        return
    if args.image:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--entrypoint",
                "python",
                "-i",
                args.image,
                "-I",
                "-",
                "--runtime",
                "--system",
                "--all-bundles",
            ],
            input=Path(__file__).read_text(),
            text=True,
            check=False,
        )
        raise SystemExit(result.returncode)
    try:
        print(
            json.dumps(
                check_environment(
                    runtime=args.runtime,
                    system=args.system,
                    all_bundles=args.all_bundles,
                ),
                indent=2,
            )
        )
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        # Error labels are portable; avoid exporting host filesystem locations.
        print(
            f"CA trust check failed: {exc}"
            if isinstance(exc, ValueError)
            else "CA trust check failed: cannot read certificate bundle",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
