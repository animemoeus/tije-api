FROM python:3.13-slim AS builder
WORKDIR /build
COPY requirements.txt .
# dev tools (pytest, ruff, pre-commit) tidak perlu di runtime
RUN grep -vE '^(pytest|ruff|pre-commit)' requirements.txt > runtime.txt \
 && python -m venv /venv \
 && /venv/bin/pip install --no-cache-dir -r runtime.txt

FROM python:3.13-slim
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /srv
COPY --from=builder /venv /venv
COPY app ./app
USER nobody
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
