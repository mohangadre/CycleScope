FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
COPY --chown=10001:10001 pyproject.toml uv.lock README.md ./
COPY --chown=10001:10001 src ./src
RUN --mount=type=secret,id=proxy_ca --mount=type=cache,target=/tmp/uv-build-cache \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    UV_CACHE_DIR=/tmp/uv-build-cache uv sync --frozen --no-dev --no-editable
COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 alembic ./alembic
USER 10001:10001
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "cyclescope.api.app:create_app", "--factory", "--host", "0.0.0.0"]
