FROM rust:1-bookworm AS builder
WORKDIR /build
COPY . .
# Cache mounts keep the registry and target dir between builds, so no dummy-main trick is needed.
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/build/target \
    cargo build --release --locked && cp target/release/tije-api /tije-api

# distroless/cc has glibc, CA certificates and a nonroot user, which is all the binary needs.
FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=builder /tije-api /tije-api
EXPOSE 8000
ENTRYPOINT ["/tije-api"]
