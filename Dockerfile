FROM ghcr.io/astral-sh/uv:0.9-debian

LABEL org.opencontainers.image.authors="celsius narhwal <hello@celsiusnarhwal.dev>"

ENV S6_KEEP_ENV=1

ARG S6_OVERLAY_VERSION=3.2.1.0

ARG TARGETARCH
ARG S6_ARCH=${TARGETARCH/amd64/x86_64}
ARG S6_ARCH=${S6_ARCH/arm64/aarch64}

ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-${S6_ARCH}.tar.xz

COPY s6/etc/ /etc/

ARG NO_REDIS
RUN if [ "${NO_REDIS}" != 1 ]; then apt-get update && apt-get install redis-server -y; else find /etc/s6-overlay -name "redis" -exec rm -rf {} +; fi

WORKDIR /app/

COPY pyproject.toml uv.lock /app/
RUN uv sync

COPY . /app/
RUN rm -rf s6/

ENTRYPOINT ["/init"]