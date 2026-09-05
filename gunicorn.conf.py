# gunicorn.conf.py
# Production Gunicorn configuration for AI Commerce OS
# Usage: gunicorn -c gunicorn.conf.py "app:create_app()"

import os
import multiprocessing

# ── Binding ───────────────────────────────────────────────────────────
bind    = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 512

# ── Workers ───────────────────────────────────────────────────────────
# Formula: (2 × CPU cores) + 1 for I/O-bound Flask.
# Cap at 8 to avoid MongoDB connection pool exhaustion.
workers     = min(int(os.environ.get("GUNICORN_WORKERS", 0)) or
                  (2 * multiprocessing.cpu_count() + 1), 8)
worker_class = "sync"          # Use "gevent" if you install greenlet
timeout      = 60              # seconds — generous for AI provider calls
keepalive    = 5

# ── Logging ───────────────────────────────────────────────────────────
loglevel       = os.environ.get("GUNICORN_LOG_LEVEL", "info")
accesslog      = "-"           # stdout → captured by systemd / Docker
errorlog       = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ── Process ───────────────────────────────────────────────────────────
preload_app  = True            # load app once, fork workers — shares in-memory rate-limit store
daemon       = False           # never daemonise; let systemd/Docker own the PID
max_requests = 1000            # restart worker after N requests (memory leak guard)
max_requests_jitter = 50

# ── Security ──────────────────────────────────────────────────────────
limit_request_line   = 8190
limit_request_fields = 100
forwarded_allow_ips  = "*"     # trust X-Forwarded-For behind Nginx/ALB
