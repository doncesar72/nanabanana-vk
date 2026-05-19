#!/usr/bin/env python3
"""Запускает Flask + VK бот через subprocess"""
import os, subprocess, sys, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# Запускаем VK бота как отдельный процесс
vk_proc = subprocess.Popen([sys.executable, "vk_bot.py"])
logger.info("VK бот запущен (PID %d)", vk_proc.pid)

# Запускаем Flask в основном процессе
import server as srv
port = int(os.environ.get("PORT", 8080))
logger.info("Flask на порту %d", port)
srv.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
