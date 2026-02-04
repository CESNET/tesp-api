# From: https://github.com/tiangolo/uvicorn-gunicorn-docker/blob/315f04413114e938ff37a410b5979126facc90af/python3.7/gunicorn_conf.py

import json
import multiprocessing
import os
import logging

from tesp_api.config import gunicorn_logger

workers_per_core_str = os.getenv("WORKERS_PER_CORE", "1")
web_concurrency_str = os.getenv("WEB_CONCURRENCY", None)
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind_env = os.getenv("BIND", None)
if bind_env:
    use_bind = bind_env
else:
    use_bind = f"{host}:{port}"
cores = multiprocessing.cpu_count()
workers_per_core = float(workers_per_core_str)
default_web_concurrency = workers_per_core * cores
if web_concurrency_str:
    web_concurrency = int(web_concurrency_str)
    assert web_concurrency > 0
else:
    web_concurrency = max(int(default_web_concurrency), 2)

# Gunicorn config variables
workers = web_concurrency
bind = use_bind
keepalive = 120
accesslog = "-"
errorlog = "-"
worker_class = "uvicorn.workers.UvicornWorker"
logger_class = gunicorn_logger.StubbedGunicornLogger

# For debugging and testing
log_data = {
    "workers": workers,
    "bind": bind,
    # Additional, non-gunicorn variables
    "workers_per_core": workers_per_core,
    "host": host,
    "port": port,
}
logging.basicConfig(level=logging.INFO)
logging.getLogger("gunicorn.config").info(json.dumps(log_data))
