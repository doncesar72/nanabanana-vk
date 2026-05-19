#!/usr/bin/env python3
import os, subprocess, sys, time, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

port = os.environ.get("PORT", "8080")

# Запускаем gunicorn напрямую как subprocess
flask_proc = subprocess.Popen([
    sys.executable, "-m", "gunicorn",
    "server:app",
    "--bind", f"0.0.0.0:{port}",
    "--workers", "1",
    "--timeout", "120",
    "--log-level", "info"
])
logger.info("Flask/gunicorn запущен (PID %d) на порту %s", flask_proc.pid, port)

# Даём gunicorn секунду подняться
time.sleep(2)

# Запускаем VK бота как subprocess
vk_proc = subprocess.Popen([sys.executable, "vk_bot.py"])
logger.info("VK бот запущен (PID %d)", vk_proc.pid)

# Ждём пока gunicorn живёт (если упадёт — перезапускаем)
while True:
    ret = flask_proc.poll()
    if ret is not None:
        logger.error("gunicorn упал с кодом %d, перезапускаю...", ret)
        flask_proc = subprocess.Popen([
            sys.executable, "-m", "gunicorn",
            "server:app",
            "--bind", f"0.0.0.0:{port}",
            "--workers", "1",
            "--timeout", "120"
        ])
    time.sleep(5)
