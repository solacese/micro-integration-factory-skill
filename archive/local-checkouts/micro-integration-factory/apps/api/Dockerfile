FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    NODE_PATH=/usr/local/lib/node_modules

ARG DOCKER_CLI_VERSION=28.0.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl default-jdk-headless maven nodejs npm tar \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && chmod +x /usr/local/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz

RUN pip install --no-cache-dir uv==0.9.5 \
    && npm install -g solclientjs@10

WORKDIR /workspace
COPY . /workspace

WORKDIR /workspace/apps/api
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["bash", "-lc", "uv run alembic upgrade head && uv run uvicorn spec2event.main:app --host 0.0.0.0 --port 8000"]
