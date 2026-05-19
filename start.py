#!/usr/bin/env python3
"""
Запускает Flask сервер (основной поток) и VK бота (daemon поток).
"""
import threading
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


def run_vk_bot():
    """VK бот в daemon потоке."""
    try:
        import vk_bot
        logger.info("Запускаю VK бота...")
        vk_bot.main()
    except Exception as e:
        logger.error("VK бот упал: %s", e, exc_info=True)


if __name__ == "__main__":
    # VK бот — daemon поток (стартует сразу)
    t = threading.Thread(target=run_vk_bot, daemon=True, name="vk-bot")
    t.start()
    logger.info("VK бот запущен в фоне")

    # Flask — основной поток (Railway держит процесс)
    import server as srv
    port = int(os.environ.get("PORT", 8080))
    logger.info("Flask запускается на порту %d", port)
    srv.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
