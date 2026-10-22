# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
# Refresh signed distribution trust data, including the emSign cross-signs.
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac AS trust
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM docker:29.7.2-dind@sha256:3ef33f2e220b79ed3ef3b99d81746f06f306cd6340e2cb7331d17ae996e74cb6 AS engine
# Replace hashed certificate directories as well as the aggregate PEM bundle.
RUN rm -rf /etc/ssl/certs /usr/share/ca-certificates
COPY --from=trust /etc/ssl/certs /etc/ssl/certs
COPY --from=trust /usr/share/ca-certificates /usr/share/ca-certificates
COPY --from=trust /usr/share/doc/ca-certificates/copyright /usr/share/licenses/dockflow-ca-certificates/COPYRIGHT

# Retain the existing registry major and storage format.
FROM registry:2.8.3@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373 AS registry
RUN rm -rf /etc/ssl/certs /usr/share/ca-certificates
COPY --from=trust /etc/ssl/certs /etc/ssl/certs
COPY --from=trust /usr/share/ca-certificates /usr/share/ca-certificates
COPY --from=trust /usr/share/doc/ca-certificates/copyright /usr/share/licenses/dockflow-ca-certificates/COPYRIGHT
