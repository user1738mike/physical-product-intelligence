"""Small-deployment bounded synchronous workers; no implicit migrations or model calls."""

bind = "0.0.0.0:8000"
workers = 2
threads = 2
timeout = 60
graceful_timeout = 45
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = None  # Django emits normalized route logs without query/header/body content.
errorlog = "-"
