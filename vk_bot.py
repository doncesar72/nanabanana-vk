#!/usr/bin/env python3
"""
🍌 Nano Banana — VK Bot
Генерация изображений через kie.ai для ВКонтакте

Установка:
  pip install vk_api requests

Запуск:
  python vk_bot.py
"""

import io
import json
import os
import random
import time
import logging
import requests
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ══════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════
VK_TOKEN    = os.environ.get("VK_TOKEN",    "ВАШ_VK_TOKEN")
VK_GROUP_ID = int(os.environ.get("VK_GROUP_ID", "238791027"))

KIE_API_KEY     = os.environ.get("KIE_API_KEY",     "ВАШ_KIE_KEY")
CREDITS_PER_GEN = int(os.environ.get("CREDITS_PER_GEN", "12"))
CREDITS_FILE    = os.environ.get("CREDITS_FILE", "vk_credits.json")
ADMIN_VK_IDS    = [int(x) for x in os.environ.get("ADMIN_VK_IDS", "5236697716").split(",")]

KIE_API_URL    = "https://api.kie.ai/api/v1"
KIE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ── Состояния пользователей ───────────────────────────────────
# user_states[user_id] = { step, prompt, aspect, resolution, model, refs }
user_states: dict = {}

# ── Модели ───────────────────────────────────────────────────
MODELS = {
    "nb2":  ("nano-banana-2",      "🍌 Nano Banana 2",   "Быстро, 4K"),
    "pro":  ("nano-banana-pro",    "🍌✨ Pro",            "Студийное качество"),
    "nb":   ("google/nano-banana", "🍌 Nano Banana",     "Самый быстрый"),
}

ASPECTS = ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"]
RESOLUTIONS = ["1K", "2K", "4K"]

# ── Популярные промпты (витрина) ──────────────────────────────
POPULAR_PROMPTS = [
    {
        "title": "🌆 Киберпанк город",
        "prompt": "Cyberpunk city at night, neon lights, rain, ultra realistic, cinematic 4K, detailed"
    },
    {
        "title": "🧝 Эльфийка",
        "prompt": "Beautiful elven girl in enchanted forest, glowing eyes, fantasy art, highly detailed, 4K"
    },
    {
        "title": "🚀 Космос",
        "prompt": "Astronaut floating in space, Earth in background, cinematic lighting, photorealistic, 4K"
    },
    {
        "title": "🐉 Дракон",
        "prompt": "Majestic dragon on mountain peak, lightning storm, epic fantasy, highly detailed, 4K"
    },
    {
        "title": "🏯 Японский храм",
        "prompt": "Ancient Japanese temple in cherry blossom forest, morning fog, cinematic, photorealistic"
    },
    {
        "title": "👤 Портрет",
        "prompt": "Professional portrait of a person, studio lighting, bokeh background, photorealistic, 4K"
    },
    {
        "title": "🌊 Подводный мир",
        "prompt": "Underwater world, colorful coral reef, tropical fish, crystal clear water, photorealistic 4K"
    },
    {
        "title": "🤖 Робот",
        "prompt": "Futuristic humanoid robot in megacity, chrome details, sci-fi, cinematic lighting, 4K"
    },
]


# ══════════════════════════════════════════════════════════════
#  СИСТЕМА КРЕДИТОВ
# ══════════════════════════════════════════════════════════════

def load_credits() -> dict:
    try:
        with open(CREDITS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_credits(data: dict):
    with open(CREDITS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_balance(user_id: int) -> int:
    return load_credits().get(str(user_id), 0)

def add_credits(user_id: int, amount: int) -> int:
    data = load_credits()
    key = str(user_id)
    data[key] = data.get(key, 0) + amount
    save_credits(data)
    return data[key]

def set_credits(user_id: int, amount: int) -> int:
    data = load_credits()
    data[str(user_id)] = amount
    save_credits(data)
    return amount

def spend_credits(user_id: int, amount: int) -> bool:
    data = load_credits()
    key = str(user_id)
    if data.get(key, 0) < amount:
        return False
    data[key] -= amount
    save_credits(data)
    return True

def is_new_user(user_id: int) -> bool:
    return str(user_id) not in load_credits()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_VK_IDS


# ══════════════════════════════════════════════════════════════
#  KIE.AI API
# ══════════════════════════════════════════════════════════════

def kie_upload(image_bytes: bytes, filename: str = "ref.jpg") -> str:
    resp = requests.post(
        KIE_UPLOAD_URL,
        headers={"Authorization": f"Bearer {KIE_API_KEY}"},
        files={"file": (filename, io.BytesIO(image_bytes), "image/jpeg")},
        data={"uploadPath": "images/references", "fileName": filename},
        timeout=60,
    )
    resp.raise_for_status()
    d = resp.json()
    url = d.get("data", {}).get("fileUrl") or d.get("fileUrl")
    if not url:
        raise ValueError(f"fileUrl not found: {d}")
    return url

def kie_create_task(model: str, prompt: str, aspect: str = "auto",
                    resolution: str = "1K", image_input: list = None) -> str:
    inp = {
        "prompt": prompt,
        "aspect_ratio": aspect,
        "resolution": resolution,
        "output_format": "jpg",
    }
    if image_input:
        field = "image_urls" if model == "google/nano-banana-edit" else "image_input"
        inp[field] = image_input

    resp = requests.post(
        f"{KIE_API_URL}/jobs/createTask",
        headers={"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"},
        json={"model": model, "input": inp},
        timeout=30,
    )
    resp.raise_for_status()
    d = resp.json()
    if d.get("code") not in (200, None):
        raise ValueError(d.get("msg", f"KIE error {d.get('code')}"))
    return d["data"]["taskId"]

def kie_poll(task_id: str, max_wait: int = 300) -> str:
    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.get(
            f"{KIE_API_URL}/jobs/recordInfo",
            headers={"Authorization": f"Bearer {KIE_API_KEY}"},
            params={"taskId": task_id},
            timeout=30,
        )
        resp.raise_for_status()
        task = resp.json().get("data") or {}
        state = (task.get("state") or "").lower()
        logger.info("Task %s — %s", task_id, state)

        if state == "success":
            rj = task.get("resultJson") or ""
            if rj:
                urls = json.loads(rj).get("resultUrls") or []
                if urls:
                    return urls[0]
        if state == "fail":
            raise ValueError(f"Generation failed: {task.get('failMsg')}")
        time.sleep(5)
    raise TimeoutError("Превышено время ожидания")


# ══════════════════════════════════════════════════════════════
#  VK ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════════════

def send(vk, user_id: int, text: str, keyboard=None, attachment=None):
    """Отправить сообщение пользователю."""
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": get_random_id(),
    }
    if keyboard:
        params["keyboard"] = keyboard.get_keyboard()
    if attachment:
        params["attachment"] = attachment
    vk.messages.send(**params)

def upload_photo_to_vk(vk_session, image_url: str, user_id: int) -> str:
    """
    Скачать картинку с URL и загрузить во ВКонтакте.
    Возвращает attachment строку вида 'photo{owner_id}_{photo_id}'
    """
    # Получаем сервер для загрузки
    upload_server = vk_session.method("photos.getMessagesUploadServer",
                                      {"peer_id": user_id})
    upload_url = upload_server["upload_url"]

    # Скачиваем картинку
    img_resp = requests.get(image_url, timeout=60)
    img_resp.raise_for_status()

    # Загружаем на VK
    up_resp = requests.post(
        upload_url,
        files={"photo": ("image.jpg", img_resp.content, "image/jpeg")},
        timeout=60,
    )
    up_data = up_resp.json()

    # Сохраняем фото
    saved = vk_session.method("photos.saveMessagesPhoto", {
        "server": up_data["server"],
        "photo":  up_data["photo"],
        "hash":   up_data["hash"],
    })
    photo = saved[0]
    return f"photo{photo['owner_id']}_{photo['id']}"


# ══════════════════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════

def kb_main() -> VkKeyboard:
    """Главное меню."""
    kb = VkKeyboard(one_time=False)
    kb.add_button("🎨 Сгенерировать", color=VkKeyboardColor.POSITIVE,
                  payload={"cmd": "generate"})
    kb.add_button("💰 Баланс", color=VkKeyboardColor.PRIMARY,
                  payload={"cmd": "balance"})
    kb.add_line()
    kb.add_button("🌟 Популярные промпты", color=VkKeyboardColor.SECONDARY,
                  payload={"cmd": "popular"})
    kb.add_button("⚙️ Настройки", color=VkKeyboardColor.SECONDARY,
                  payload={"cmd": "settings"})
    kb.add_line()
    kb.add_button("❓ Помощь", color=VkKeyboardColor.SECONDARY,
                  payload={"cmd": "help"})
    return kb

def kb_aspects() -> VkKeyboard:
    kb = VkKeyboard(one_time=True)
    row = []
    for i, a in enumerate(ASPECTS):
        kb.add_button(a, color=VkKeyboardColor.PRIMARY,
                      payload={"cmd": "aspect", "val": a})
        if (i + 1) % 4 == 0 and i < len(ASPECTS) - 1:
            kb.add_line()
    return kb

def kb_resolutions() -> VkKeyboard:
    kb = VkKeyboard(one_time=True)
    for r in RESOLUTIONS:
        kb.add_button(r, color=VkKeyboardColor.PRIMARY,
                      payload={"cmd": "res", "val": r})
    return kb

def kb_models() -> VkKeyboard:
    kb = VkKeyboard(one_time=True)
    for key, (_, name, desc) in MODELS.items():
        kb.add_button(f"{name} — {desc}", color=VkKeyboardColor.PRIMARY,
                      payload={"cmd": "model", "val": key})
        kb.add_line()
    return kb

def kb_popular() -> VkKeyboard:
    kb = VkKeyboard(one_time=True)
    for i, p in enumerate(POPULAR_PROMPTS):
        kb.add_button(p["title"], color=VkKeyboardColor.SECONDARY,
                      payload={"cmd": "use_prompt", "idx": i})
        if (i + 1) % 2 == 0 and i < len(POPULAR_PROMPTS) - 1:
            kb.add_line()
    kb.add_line()
    kb.add_button("↩ Назад", color=VkKeyboardColor.NEGATIVE,
                  payload={"cmd": "back"})
    return kb

def kb_back() -> VkKeyboard:
    kb = VkKeyboard(one_time=True)
    kb.add_button("↩ Назад в меню", color=VkKeyboardColor.SECONDARY,
                  payload={"cmd": "back"})
    return kb


# ══════════════════════════════════════════════════════════════
#  ОБРАБОТЧИКИ КОМАНД
# ══════════════════════════════════════════════════════════════

def handle_start(vk, user_id: int):
    """Первый запуск или команда /start."""
    new = is_new_user(user_id)
    if new:
        add_credits(user_id, CREDITS_PER_GEN)
        welcome_extra = (
            f"\n\n🎁 Тебе начислено *{CREDITS_PER_GEN} приветственных кредитов* "
            f"— хватит на одну генерацию!"
        )
    else:
        bal = get_balance(user_id)
        welcome_extra = f"\n\n💰 Твой баланс: {bal} кредитов"

    text = (
        "👋 Привет! Я генерирую изображения с помощью ИИ — Nano Banana от Google.\n\n"
        "📸 Просто опиши что хочешь увидеть — и я создам картинку!\n\n"
        "Можешь также:\n"
        "• Выбрать один из популярных промптов\n"
        "• Настроить соотношение сторон и разрешение\n"
        "• Загрузить референс-фото для стиля"
        + welcome_extra
    )
    send(vk, user_id, text, keyboard=kb_main())


def handle_balance(vk, user_id: int):
    bal = get_balance(user_id)
    send(vk, user_id,
         f"💰 Твой баланс: {bal} кредитов\n\n"
         f"💸 Стоимость генерации: {CREDITS_PER_GEN} кредитов\n\n"
         "Для пополнения напиши администратору.",
         keyboard=kb_main())


def handle_popular(vk, user_id: int):
    text = "🌟 Популярные промпты — выбери один и сразу попробуй!\n\n"
    for i, p in enumerate(POPULAR_PROMPTS):
        text += f"{p['title']}\n_{p['prompt'][:80]}..._\n\n"
    send(vk, user_id, text, keyboard=kb_popular())


def handle_settings(vk, user_id: int):
    state = user_states.get(user_id, {})
    model_key = state.get("model", "nb2")
    model_name = MODELS[model_key][1]
    aspect = state.get("aspect", "auto")
    res = state.get("resolution", "1K")
    refs = len(state.get("refs", []))

    send(vk, user_id,
         f"⚙️ Текущие настройки:\n\n"
         f"🤖 Модель: {model_name}\n"
         f"📐 Соотношение: {aspect}\n"
         f"🔍 Разрешение: {res}\n"
         f"🖼 Референсов: {refs}/14\n\n"
         "Выбери что изменить:",
         keyboard=kb_models())


def handle_help(vk, user_id: int):
    send(vk, user_id,
         "❓ Как пользоваться:\n\n"
         "1️⃣ Нажми «Сгенерировать»\n"
         "2️⃣ Напиши промпт (описание картинки)\n"
         "3️⃣ Выбери соотношение сторон\n"
         "4️⃣ Выбери разрешение\n"
         "5️⃣ Жди ~30-60 секунд 🎨\n\n"
         "💡 Советы для промптов:\n"
         "• Пиши на английском — лучше результат\n"
         "• Добавь стиль: realistic, anime, oil painting\n"
         "• Укажи освещение: cinematic lighting, neon glow\n"
         "• Добавь качество: 4K, highly detailed, photorealistic\n\n"
         "Пример: Cyberpunk girl in Tokyo, neon lights, rain, 4K",
         keyboard=kb_main())


def start_generate(vk, user_id: int):
    """Начать процесс генерации."""
    bal = get_balance(user_id)
    if bal < CREDITS_PER_GEN:
        send(vk, user_id,
             f"❌ Недостаточно кредитов.\n\n"
             f"💰 Твой баланс: {bal} кред.\n"
             f"💸 Нужно: {CREDITS_PER_GEN} кред.\n\n"
             "Для пополнения напиши администратору.",
             keyboard=kb_main())
        return

    # Инициализируем состояние
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]["step"] = "wait_prompt"

    send(vk, user_id,
         "✏️ Напиши промпт — опиши что хочешь сгенерировать.\n\n"
         "Пиши на английском для лучшего результата:\n"
         "_Пример: Beautiful girl in Tokyo street, neon lights, rain, cinematic 4K_",
         keyboard=kb_back())


def handle_prompt_received(vk, user_id: int, text: str):
    """Пользователь ввёл промпт."""
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]["prompt"] = text
    user_states[user_id]["step"] = "wait_aspect"

    send(vk, user_id,
         f"📝 Промпт: «{text[:100]}»\n\n"
         "📐 Выбери соотношение сторон:",
         keyboard=kb_aspects())


def handle_aspect_selected(vk, user_id: int, aspect: str):
    """Пользователь выбрал соотношение."""
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]["aspect"] = aspect
    user_states[user_id]["step"] = "wait_resolution"

    send(vk, user_id,
         f"📐 Соотношение: {aspect}\n\n"
         "🔍 Выбери разрешение:",
         keyboard=kb_resolutions())


def handle_resolution_selected(vk, vk_session, user_id: int, resolution: str):
    """Пользователь выбрал разрешение — запускаем генерацию."""
    state = user_states.get(user_id, {})
    state["resolution"] = resolution
    state["step"] = "generating"

    prompt     = state.get("prompt", "")
    aspect     = state.get("aspect", "auto")
    model_key  = state.get("model", "nb2")
    model_id   = MODELS[model_key][0]
    model_name = MODELS[model_key][1]
    refs       = state.get("refs", [])

    send(vk, user_id,
         f"🎨 Генерирую...\n\n"
         f"🤖 {model_name}\n"
         f"📐 {aspect} | 🔍 {resolution}\n"
         f"📝 {prompt[:100]}\n\n"
         "Подожди ~30-90 секунд ⏳")

    try:
        # Проверяем баланс ещё раз
        if not spend_credits(user_id, CREDITS_PER_GEN):
            send(vk, user_id, "❌ Недостаточно кредитов.", keyboard=kb_main())
            return

        task_id   = kie_create_task(model_id, prompt, aspect, resolution,
                                    refs if refs else None)
        image_url = kie_poll(task_id)
        attachment = upload_photo_to_vk(vk_session, image_url, user_id)
        new_bal = get_balance(user_id)

        send(vk, user_id,
             f"✅ Готово!\n"
             f"🤖 {model_name} | 📐 {aspect} | 🔍 {resolution}\n"
             f"📝 {prompt[:150]}\n\n"
             f"💰 Остаток: {new_bal} кредитов",
             keyboard=kb_main(),
             attachment=attachment)

    except TimeoutError:
        # Возвращаем кредиты при таймауте
        add_credits(user_id, CREDITS_PER_GEN)
        send(vk, user_id,
             "❌ Генерация заняла слишком долго.\n"
             "Кредиты возвращены. Попробуй ещё раз.",
             keyboard=kb_main())
    except Exception as e:
        # Возвращаем кредиты при ошибке
        add_credits(user_id, CREDITS_PER_GEN)
        logger.error("Generation error for %s: %s", user_id, e, exc_info=True)
        send(vk, user_id,
             f"❌ Ошибка генерации: {e}\nКредиты возвращены.",
             keyboard=kb_main())
    finally:
        state["step"] = None


# ── Админ-команды ─────────────────────────────────────────────

def handle_admin(vk, user_id: int, text: str):
    """Обработка админских команд."""
    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""

    if cmd == "/addcredits" and len(parts) == 3:
        try:
            target = int(parts[1])
            amount = int(parts[2])
            new_bal = add_credits(target, amount)
            send(vk, user_id,
                 f"✅ Начислено {amount} кред. пользователю {target}\n"
                 f"Новый баланс: {new_bal}")
            # Уведомить пользователя
            try:
                send(vk, target,
                     f"🎁 Тебе начислено {amount} кредитов!\n"
                     f"Твой баланс: {new_bal} кред.",
                     keyboard=kb_main())
            except Exception:
                pass
        except ValueError:
            send(vk, user_id, "Использование: /addcredits <user_id> <amount>")

    elif cmd == "/setcredits" and len(parts) == 3:
        try:
            target = int(parts[1])
            amount = int(parts[2])
            set_credits(target, amount)
            send(vk, user_id, f"✅ Баланс {target} установлен: {amount} кред.")
        except ValueError:
            send(vk, user_id, "Использование: /setcredits <user_id> <amount>")

    elif cmd == "/users":
        data = load_credits()
        if not data:
            send(vk, user_id, "Пользователей пока нет.")
            return
        lines = ["👥 Пользователи:\n"]
        for uid, bal in sorted(data.items(), key=lambda x: -x[1]):
            lines.append(f"• {uid} — {bal} кред.")
        send(vk, user_id, "\n".join(lines))

    elif cmd == "/bal" and len(parts) == 2:
        try:
            target = int(parts[1])
            bal = get_balance(target)
            send(vk, user_id, f"💰 Баланс {target}: {bal} кред.")
        except ValueError:
            send(vk, user_id, "Использование: /bal <user_id>")

    else:
        send(vk, user_id,
             "🔧 Команды администратора:\n\n"
             "/addcredits <id> <кол-во> — начислить\n"
             "/setcredits <id> <кол-во> — установить\n"
             "/bal <id> — проверить баланс\n"
             "/users — все пользователи")


# ══════════════════════════════════════════════════════════════
#  ОСНОВНОЙ ОБРАБОТЧИК СОБЫТИЙ
# ══════════════════════════════════════════════════════════════

def handle_event(vk, vk_session, event):
    """Обработать одно событие от VK."""
    if event.type != VkBotEventType.MESSAGE_NEW:
        return

    msg     = event.obj.message
    user_id = msg["from_id"]
    text    = msg.get("text", "").strip()
    payload = json.loads(msg.get("payload", "{}"))
    attachments = msg.get("attachments", [])

    # Игнорируем сообщения из бесед
    if user_id < 0:
        return

    logger.info("Message from %s: %r payload=%s", user_id, text[:50], payload)

    # ── Фото (референс) ──────────────────────────────────────
    if attachments:
        for att in attachments:
            if att.get("type") == "photo":
                state = user_states.setdefault(user_id, {})
                refs  = state.setdefault("refs", [])
                if len(refs) >= 14:
                    send(vk, user_id, "⚠️ Достигнут лимит 14 референсов.")
                    return

                # Берём максимальный размер фото
                sizes = att["photo"].get("sizes", [])
                if not sizes:
                    continue
                best = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
                img_url = best["url"]

                try:
                    img_data = requests.get(img_url, timeout=30).content
                    file_url = kie_upload(img_data,
                                          f"ref_{att['photo']['id']}.jpg")
                    refs.append(file_url)
                    send(vk, user_id,
                         f"✅ Референс загружен! {len(refs)}/14\n"
                         "Напиши промпт или нажми «Сгенерировать».",
                         keyboard=kb_main())
                except Exception as e:
                    send(vk, user_id, f"❌ Не удалось загрузить референс: {e}")
                return

    # ── Команды через payload (кнопки) ───────────────────────
    cmd = payload.get("cmd", "")

    if cmd == "generate" or text.lower() in ("сгенерировать", "/generate"):
        start_generate(vk, user_id)
        return

    if cmd == "balance" or text.lower() in ("баланс", "/balance", "/bal"):
        handle_balance(vk, user_id)
        return

    if cmd == "popular" or text.lower() in ("популярные промпты", "/popular"):
        handle_popular(vk, user_id)
        return

    if cmd == "settings" or text.lower() in ("настройки", "/settings"):
        handle_settings(vk, user_id)
        return

    if cmd == "help" or text.lower() in ("помощь", "/help", "помоги"):
        handle_help(vk, user_id)
        return

    if cmd == "back" or text.lower() in ("назад", "/start", "начало", "меню"):
        user_states.pop(user_id, None)
        handle_start(vk, user_id)
        return

    # Выбор соотношения
    if cmd == "aspect":
        handle_aspect_selected(vk, user_id, payload["val"])
        return

    # Выбор разрешения
    if cmd == "res":
        handle_resolution_selected(vk, vk_session, user_id, payload["val"])
        return

    # Выбор модели
    if cmd == "model":
        state = user_states.setdefault(user_id, {})
        state["model"] = payload["val"]
        model_name = MODELS[payload["val"]][1]
        send(vk, user_id,
             f"✅ Модель выбрана: {model_name}",
             keyboard=kb_main())
        return

    # Использовать популярный промпт
    if cmd == "use_prompt":
        idx    = payload.get("idx", 0)
        prompt = POPULAR_PROMPTS[idx]["prompt"]
        title  = POPULAR_PROMPTS[idx]["title"]
        state  = user_states.setdefault(user_id, {})
        state["prompt"] = prompt
        state["step"]   = "wait_aspect"
        send(vk, user_id,
             f"✨ Выбран промпт: {title}\n"
             f"📝 {prompt}\n\n"
             "📐 Выбери соотношение сторон:",
             keyboard=kb_aspects())
        return

    # ── Очистить референсы ───────────────────────────────────
    if text.lower() in ("/refs", "референсы", "очистить референсы"):
        state = user_states.get(user_id, {})
        state["refs"] = []
        user_states[user_id] = state
        send(vk, user_id, "🗑 Референсы очищены.", keyboard=kb_main())
        return

    # ── Админ-команды ────────────────────────────────────────
    if is_admin(user_id) and text.startswith("/"):
        handle_admin(vk, user_id, text)
        return

    # ── Обработка по текущему шагу ───────────────────────────
    state = user_states.get(user_id, {})
    step  = state.get("step")

    if step == "wait_prompt" and text:
        handle_prompt_received(vk, user_id, text)
        return

    if step == "wait_aspect":
        # Пользователь написал соотношение текстом
        if text in ASPECTS:
            handle_aspect_selected(vk, user_id, text)
        else:
            send(vk, user_id,
                 "Пожалуйста, выбери соотношение из кнопок ниже 👇",
                 keyboard=kb_aspects())
        return

    if step == "wait_resolution":
        if text in RESOLUTIONS:
            handle_resolution_selected(vk, vk_session, user_id, text)
        else:
            send(vk, user_id,
                 "Пожалуйста, выбери разрешение из кнопок ниже 👇",
                 keyboard=kb_resolutions())
        return

    # ── По умолчанию — если написал текст без контекста ─────
    if text:
        # Если похоже на промпт — сразу начинаем генерацию
        if len(text) > 5 and not text.startswith("/"):
            state = user_states.setdefault(user_id, {})
            bal = get_balance(user_id)
            if bal < CREDITS_PER_GEN:
                send(vk, user_id,
                     f"❌ Недостаточно кредитов ({bal}/{CREDITS_PER_GEN}).\n"
                     "Для пополнения напиши администратору.",
                     keyboard=kb_main())
                return
            state["prompt"] = text
            state["step"]   = "wait_aspect"
            send(vk, user_id,
                 f"📝 Промпт: «{text[:100]}»\n\n"
                 "📐 Выбери соотношение сторон:",
                 keyboard=kb_aspects())
        else:
            handle_start(vk, user_id)


# ══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════

def main():
    logger.info("Запуск VK бота Nano Banana...")

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk         = vk_session.get_api()
    longpoll   = VkBotLongPoll(vk_session, VK_GROUP_ID)

    logger.info("Бот запущен! Слушаю события...")

    for event in longpoll.listen():
        try:
            handle_event(vk, vk_session, event)
        except Exception as e:
            logger.error("Unhandled error: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
