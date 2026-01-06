FROM ghcr.io/astral-sh/uv:0.9-debian

ARG S6_OVERLAY_VERSION=3.2.1.0

WORKDIR /app/

ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-aarch64.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-aarch64.tar.xz

RUN apt-get update && apt-get install redis-server -y

COPY pyproject.toml uv.lock /app/
RUN uv sync

COPY s6/etc/ /etc

WORKDIR /etc/s6-overlay/s6-rc.d/user/contents.d
RUN touch scheduler redis

WORKDIR /app/

COPY . /app/

CMD ["with-contenv", "uv", "run", "taskiq", "worker", "terebii.app:broker"]

ENTRYPOINT ["/init"]