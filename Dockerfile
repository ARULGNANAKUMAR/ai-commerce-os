# ── Dockerfile ────────────────────────────────────────────────────
# Multi-stage: install deps first for layer-cache efficiency.
# Stage 1: dependency builder
FROM python:3.11-slim AS builder
WORKDIR /install
COPY requirements.txt .
RUN pip install --prefix=/install/pkgs --no-cache-dir -r requirements.txt

# Stage 2: runtime image
FROM python:3.11-slim
LABEL maintainer="AI Commerce OS"
LABEL description="AI Commerce OS — SaaS AI Shopping Platform"

# Non-root user for security
RUN addgroup --system acos && adduser --system --ingroup acos acos

WORKDIR /app
COPY --from=builder /install/pkgs /usr/local
COPY . .

# Ensure static files are world-readable
RUN chown -R acos:acos /app

USER acos

EXPOSE 8000

# Gunicorn with the project's gunicorn.conf.py
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:create_app()"]
