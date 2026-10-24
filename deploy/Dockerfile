# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
ARG WHEEL_SOURCE=source-wheels
# Retain the qualified Ubuntu base and patched runtime trust stores.
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac AS dependencies
ENV DEBIAN_FRONTEND=noninteractive UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
RUN uv python install 3.13.17
WORKDIR /opt/dockflow
COPY pyproject.toml uv.lock .python-version ./
COPY packages/database/pyproject.toml packages/database/README.md packages/database/LICENSE packages/database/
COPY packages/cli/pyproject.toml packages/cli/README.md packages/cli/LICENSE packages/cli/
COPY packages/pipelines/pyproject.toml packages/pipelines/README.md packages/pipelines/LICENSE packages/pipelines/
COPY packages/artifacts/pyproject.toml packages/artifacts/README.md packages/artifacts/LICENSE packages/artifacts/
RUN uv sync --locked --python 3.13.17 --all-packages --all-extras --no-dev --no-install-workspace
# Botocore still ships the AAA cross-signing root. Align its fallback bundle for
# direct SDK users too; Dockflow S3 clients explicitly select maintained certifi.
RUN .venv/bin/python -c "import botocore,certifi,pathlib,shutil; shutil.copyfile(certifi.where(), pathlib.Path(botocore.__file__).with_name('cacert.pem'))"
COPY tools/check_ca_trust.py /tmp/check_ca_trust.py
RUN .venv/bin/python /tmp/check_ca_trust.py --runtime --all-bundles --system

FROM dependencies AS source-wheels
COPY packages/database/src packages/database/src
COPY packages/cli/src packages/cli/src
COPY packages/pipelines/src packages/pipelines/src
COPY packages/artifacts/src packages/artifacts/src
RUN uv build --all-packages --force-pep517 --out-dir /dist

# Release builds supply the already verified wheels as a named build context.
# The default source build does not resolve this unused stage/context.
FROM scratch AS supplied-wheels
COPY --from=release-wheels / /dist/

FROM ${WHEEL_SOURCE} AS selected-wheels
FROM dependencies AS build
COPY --from=selected-wheels /dist /dist
RUN uv pip install --python .venv/bin/python --no-deps /dist/*.whl

FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac AS runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    PATH=/opt/dockflow/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 dockflow && useradd --uid 10001 --gid 10001 --create-home dockflow
COPY --from=build /opt/python /opt/python
COPY --from=build /opt/dockflow/.venv /opt/dockflow/.venv
COPY LICENSE /usr/share/licenses/dockflow/LICENSE
COPY tools/check_ca_trust.py /tmp/check_ca_trust.py
RUN python /tmp/check_ca_trust.py --runtime --all-bundles --system && rm /tmp/check_ca_trust.py
ARG SOURCE_REVISION=unavailable
ARG SPECIFICATION=unfinalized
ARG IMPLEMENTATION=unaccepted-development
LABEL org.opencontainers.image.title="Dockflow Pipelines service" \
      org.opencontainers.image.source="https://github.com/dockflow-project/dockflow" \
      org.opencontainers.image.revision=$SOURCE_REVISION \
      org.opencontainers.image.version="0.1.1" \
      org.opencontainers.image.licenses="MIT" \
      io.macrostates.specification=$SPECIFICATION \
      io.macrostates.implementation=$IMPLEMENTATION
USER 10001:10001
WORKDIR /home/dockflow
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=2)"
ENTRYPOINT ["dockflow", "pipelines"]
CMD ["--config", "/config/dockflow.toml", "serve", "--host", "0.0.0.0", "--port", "8080"]
