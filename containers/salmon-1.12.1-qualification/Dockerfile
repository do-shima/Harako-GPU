FROM quay.io/biocontainers/salmon@sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e

ARG SALMON_ASSET_URL="https://github.com/COMBINE-lab/salmon/releases/download/v1.12.1/salmon-linux-x86_64.tar.gz"
ARG SALMON_ASSET_SHA256="00900135ecca10b45e3d78a6ab64463f957d0b2b0069eaa078c10784f1e2f8d6"
ARG LOCALES_ASSET_URL="https://security.debian.org/debian-security/pool/updates/main/g/glibc/locales-all_2.36-9%2Bdeb12u7_amd64.deb"
ARG LOCALES_ASSET_SHA256="407942f8edd746e3c6545f1d068ff21765609b47f5554f1e2993f612c6b64f77"

LABEL org.opencontainers.image.title="Harako-GPU Salmon 1.12.1 qualification candidate" \
      org.opencontainers.image.version="1.12.1" \
      org.opencontainers.image.revision="971a2ad6e86cc32315d919faed0be0e88d36c9e5" \
      org.opencontainers.image.source="https://github.com/COMBINE-lab/salmon" \
      org.opencontainers.image.licenses="GPL-3.0-only" \
      io.harako-gpu.qualification-only="true" \
      io.harako-gpu.asset-sha256="00900135ecca10b45e3d78a6ab64463f957d0b2b0069eaa078c10784f1e2f8d6" \
      io.harako-gpu.locales-sha256="407942f8edd746e3c6545f1d068ff21765609b47f5554f1e2993f612c6b64f77" \
      io.harako-gpu.base-digest="sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"

ENV LANG="en_US.UTF-8" \
    LC_ALL="en_US.UTF-8" \
    LD_LIBRARY_PATH="/usr/local/lib"

RUN wget -O /tmp/locales-all.deb "${LOCALES_ASSET_URL}" \
    && echo "${LOCALES_ASSET_SHA256}  /tmp/locales-all.deb" | sha256sum -c - \
    && dpkg-deb -x /tmp/locales-all.deb /tmp/locales-all \
    && cp -a /tmp/locales-all/usr/lib/locale/. /usr/lib/locale/ \
    && rm -rf /tmp/locales-all /tmp/locales-all.deb \
    && locale -a | grep -Fxi "en_US.utf8"

RUN wget -O /tmp/salmon-linux-x86_64.tar.gz "${SALMON_ASSET_URL}" \
    && echo "${SALMON_ASSET_SHA256}  /tmp/salmon-linux-x86_64.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/salmon-1.12.1 \
    && tar -xzf /tmp/salmon-linux-x86_64.tar.gz --strip-components=1 -C /opt/salmon-1.12.1 \
    && rm /tmp/salmon-linux-x86_64.tar.gz \
    && /opt/salmon-1.12.1/bin/salmon --version | grep -Fx "salmon 1.12.1"

ENV PATH="/opt/salmon-1.12.1/bin:${PATH}"

RUN salmon --version | grep -Fx "salmon 1.12.1"

COPY entrypoint.sh /usr/local/harako-salmon-env-execute
RUN chmod 0555 /usr/local/harako-salmon-env-execute

ENTRYPOINT ["/usr/local/harako-salmon-env-execute"]
