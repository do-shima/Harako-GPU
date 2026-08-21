FROM quay.io/biocontainers/salmon@sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e AS fetch

ARG SALMON_ASSET_URL="https://github.com/COMBINE-lab/salmon/releases/download/v2.5.1/salmon-cli-x86_64-unknown-linux-gnu.tar.xz"
ARG SALMON_ASSET_SHA256="6ad2a01b2022092f88f4c95601d19751e594dd3aa7be77ee7c11c1abf4842cbe"

RUN wget -O /tmp/salmon.tar.xz "${SALMON_ASSET_URL}" \
    && echo "${SALMON_ASSET_SHA256}  /tmp/salmon.tar.xz" | sha256sum -c - \
    && mkdir -p /opt/salmon-2.5.1 \
    && tar -xJf /tmp/salmon.tar.xz --strip-components=1 -C /opt/salmon-2.5.1 \
    && rm /tmp/salmon.tar.xz \
    && /opt/salmon-2.5.1/salmon --version | grep -Fx "salmon 2.5.1"

FROM debian@sha256:b1a741487078b369e78119849663d7f1a5341ef2768798f7b7406c4240f86aef

LABEL org.opencontainers.image.title="Harako-GPU Salmon 2.5.1 qualification candidate" \
      org.opencontainers.image.version="2.5.1" \
      org.opencontainers.image.revision="c360459bbf16e649a5c10c097e59f3c72e6b2e3c" \
      org.opencontainers.image.source="https://github.com/COMBINE-lab/salmon" \
      org.opencontainers.image.licenses="BSD-3-Clause" \
      io.harako-gpu.qualification-only="true" \
      io.harako-gpu.asset-sha256="6ad2a01b2022092f88f4c95601d19751e594dd3aa7be77ee7c11c1abf4842cbe" \
      io.harako-gpu.source-archive-sha256="6adde21a2baa6d0c3b8725e3180f7228b2c8a913668a81130990e6fb4dbd6036" \
      io.harako-gpu.base-digest="sha256:b1a741487078b369e78119849663d7f1a5341ef2768798f7b7406c4240f86aef"

COPY --from=fetch /opt/salmon-2.5.1 /opt/salmon-2.5.1
COPY --from=fetch /usr/bin/ps /usr/bin/ps

ENV PATH="/opt/salmon-2.5.1:${PATH}"

RUN salmon --version | grep -Fx "salmon 2.5.1" \
    && ps >/dev/null

CMD ["salmon", "--help"]
