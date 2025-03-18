import multiprocessing

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"
timeout = 120
keepalive = 5
errorlog = "gunicorn-error.log"
accesslog = "gunicorn-access.log"
loglevel = "info"
