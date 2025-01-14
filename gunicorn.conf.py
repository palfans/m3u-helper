import os
import multiprocessing

# 绑定的地址和端口
bind = "0.0.0.0:5000"

# 工作进程数
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count() * 2 + 1))

# 工作模式
worker_class = "sync"

# 超时时间
timeout = int(os.getenv("TIMEOUT", 30))

# keepalive超时
keepalive = int(os.getenv("KEEP_ALIVE", 5))

# 最大请求数
max_requests = int(os.getenv("MAX_REQUESTS", 1000))
max_requests_jitter = int(os.getenv("MAX_REQUESTS_JITTER", 50))

# 日志配置
accesslog = "-"  # 标准输出
errorlog = "-"   # 标准错误输出
loglevel = "info"

# 进程名称
proc_name = "m3u-helper"

# 优雅的重启
graceful_timeout = 30

# 预加载应用
preload_app = True 