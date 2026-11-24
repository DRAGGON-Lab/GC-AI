"""One detector and one admission slot per process. Never preload GPU state."""

import os

bind = os.getenv("GCAI_BIND", "127.0.0.1:5001")
workers = 1
threads = 4
worker_class = "gthread"
preload_app = False
backlog = 16
timeout = 180
graceful_timeout = 30
accesslog = None
errorlog = "-"
# Exclude query strings and authorization from any operator-enabled access log.
access_log_format = "%(h)s %(m)s %(U)s %(s)s %(L)s"
umask = 0o077
