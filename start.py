#!/usr/bin/env python3
"""
Запускает Flask сервер и VK бота одновременно в одном процессе.
Flask — в основном потоке (нужен Railway для web сервиса).
VK бот — в отдельном daemon потоке.
"""
import threading
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def run_vk_bot():
    """Запустить VK бота в отдельном потоке."""
    try:
        # Импортируем main из vk_bot.py и запускаем
        import vk_bot
        logger.info("Запускаю VK бота...")
        vk_bot.main()
    except Exception as e:
        logger.error("VK бот упал: %s", e, exc_info=True)


def run_server():
    """Запустить Flask сервер в основном потоке."""
    try:
        import server as srv
        port = int(os.environ.get("PORT", 8080))
        logger.info("Запускаю Flask сервер на порту %d...", port)
        srv.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error("Flask сервер упал: %s", e, exc_info=True)


if __name__ == "__main__":
    # VK бот — daemon поток (умрёт вместе с основным процессом)
    vk_thread = threading.Thread(target=run_vk_bot, daemon=True, name="vk-bot")
    vk_thread.start()
    logger.info("VK бот запущен в фоне")

    # Flask — основной поток (Railway держит процесс живым пока он работает)
    run_server()
