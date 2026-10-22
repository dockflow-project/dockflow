# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
# Preserve upstream OIDC, upload and PEP 740 attestation implementation/licenses.
FROM ghcr.io/pypa/gh-action-pypi-publish:7245906fb61fa33a13554f9d5fb856fe61758086@sha256:411241df99067c98b6d08fd8e26d14e86740a22460599c2af571e6dc26e27ffc AS upstream
FROM python:3.13.17-slim@sha256:fe14fd57a4c0361110eaa0c284112b189750bcb43fb04bb5d1ee7b7744027ccf
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=upstream /root/.local /root/.local
COPY --from=upstream /app /app
# Use the patched base pip/ensurepip instead of the publisher's old user pip.
RUN rm -rf /root/.local/lib/python3.13/site-packages/pip \
    /root/.local/lib/python3.13/site-packages/pip-*.dist-info \
    /root/.local/bin/pip /root/.local/bin/pip3 /root/.local/bin/pip3.13
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/root/.local/lib/python3.13/site-packages
COPY tools/check_ca_trust.py /tmp/check_ca_trust.py
RUN python /tmp/check_ca_trust.py --all-bundles --system && rm /tmp/check_ca_trust.py
WORKDIR /github/workspace
ENTRYPOINT ["/app/twine-upload.sh"]
