"""Gunicorn configuration for multi-worker deployment."""
import os

# Worker settings
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))  # 4 workers for multi-core
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
keepalive = 5
preload_app = False

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# Max requests before restart (prevent memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Server name
server_header = "DTSV/1.0"
