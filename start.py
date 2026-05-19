#!/usr/bin/env python3
import threading, logging, os, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

def run_vk_bot():
    time.sleep(5)
    try:
        import vk_bot
        logger.info("Запускаю VK бота...")
        vk_bot.main()
    except Exception as e:
        logger.error("VK бот упал: %s", e, exc_info=True)

t = threading.Thread(target=run_vk_bot, daemon=True, name="vk-bot")
t.start()

import server as srv
port = int(os.environ.get("PORT", 8080))
logger.info("Flask на порту %d", port)
srv.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
