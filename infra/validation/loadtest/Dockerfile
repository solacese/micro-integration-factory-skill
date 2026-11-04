FROM golang:1.27.3-bookworm AS build
WORKDIR /client
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=1 go test -mod=mod ./... && CGO_ENABLED=1 go build -mod=mod -trimpath -ldflags='-s -w' -o /loadtest .
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 && rm -rf /var/lib/apt/lists/*
COPY --from=build /loadtest /loadtest
USER 65532:65532
ENTRYPOINT ["/loadtest"]
