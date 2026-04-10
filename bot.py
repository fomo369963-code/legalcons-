from dotenv import load_dotenv
load_dotenv()
import os
import asyncio
import time
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction, ParseMode
import anthropic

# ─── Конфигурация ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "ВАШ_ANTHROPIC_KEY_ЗДЕСЬ")

# ─── Настройки защиты от абуза ───────────────────────────────────────────────
RATE_LIMIT_MESSAGES = 10        # макс сообщений за окно
RATE_LIMIT_WINDOW   = 60        # окно в секундах
RATE_LIMIT_COOLDOWN = 300       # бан на 5 минут после превышения
MAX_MESSAGE_LENGTH  = 1000      # макс символов в одном сообщении
MAX_HISTORY         = 20        # макс сообщений в контексте диалога

# Whitelist: если не пустой — бот отвечает ТОЛЬКО этим user_id
# Например: WHITELIST = {123456789, 987654321}
WHITELIST: set[int] = set()

# ─── Хранилища ───────────────────────────────────────────────────────────────
user_histories:  dict[int, list]  = {}
rate_limit_data: dict[int, list]  = defaultdict(list)
blocked_users:   dict[int, float] = {}

# ─── Клиент Anthropic ────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── Системный промпт ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ты — Юридический Советник ИИ, сверхэкспертная система в области российского права.

ТВОЯ РОЛЬ И ОГРАНИЧЕНИЯ:
Ты отвечаешь ТОЛЬКО на вопросы, связанные с правом и законодательством РФ.
Если вопрос не относится к юридической теме — вежливо откажи одним предложением и напомни свою специализацию.
НЕ юридические темы: рецепты, погода, математика, программирование, переводы, стихи, развлечения.
Юридические темы (отвечай): законы, права, суды, штрафы, договоры, наследство, трудовые споры, налоги, недвижимость, ДТП, бизнес-регуляции, потребительские права.

ТВОЯ ЭКСПЕРТИЗА: ГК РФ (ч.1-4), УК РФ, ТК РФ, КоАП РФ, СК РФ, ЖК РФ, НК РФ, ЗК РФ, АПК РФ, ГПК РФ, УПК РФ, КАС РФ, все федеральные законы.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ФОРМАТИРОВАНИЕ (СТРОГО)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ты пишешь для Telegram. Используй ТОЛЬКО:
— *жирный* для заголовков разделов
— _курсив_ для цитат и определений
— `моноширный` для номеров статей
— символы: •, —, ✓, 📌, ⚠️, цифры для списков

СТРОГО ЗАПРЕЩЕНО:
— Таблицы (| col | col |) — в Telegram выглядят как мусор, никогда не используй
— Заголовки ### ## # — не работают в Telegram
— Горизонтальные линии ---

ВМЕСТО ТАБЛИЦ — блочное сравнение. Пример:

*🔴 Ничтожная сделка*
• Недействительна сразу, автоматически
• Оспорить может любое заинтересованное лицо
• Срок давности — `3 года` (`ст. 181 ГК РФ`)

*🟡 Оспоримая сделка*
• Недействительна только после решения суда
• Оспорить могут только лица, указанные в законе
• Срок давности — `1 год` (`ст. 181 ГК РФ`)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
СТРУКТУРА КАЖДОГО ОТВЕТА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*⚖️ Суть*
1-2 предложения о чём речь

*📋 Нормы закона*
`ст. XX КодексРФ` — что регулирует

*🔍 Разбор*
Детальный анализ. Сравнения — блоками, не таблицами.

*✅ Что делать*
1. Первый шаг
2. Второй шаг

*📌 Итог*
1-2 строки — главный вывод

*🔗 Читать закон на КонсультантПлюс*
[Название статьи](ссылка)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ССЫЛКИ НА КОНСУЛЬТАНТПЛЮС
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Давай кликабельные ссылки на ВСЕ упомянутые статьи. Формат: [ст. 123 ГК РФ](URL)

ГК РФ ч.1: https://www.consultant.ru/document/cons_doc_LAW_5142/
ГК РФ ч.2: https://www.consultant.ru/document/cons_doc_LAW_9027/
ТК РФ: https://www.consultant.ru/document/cons_doc_LAW_34683/
УК РФ: https://www.consultant.ru/document/cons_doc_LAW_10699/
КоАП РФ: https://www.consultant.ru/document/cons_doc_LAW_34661/
СК РФ: https://www.consultant.ru/document/cons_doc_LAW_8982/
ЖК РФ: https://www.consultant.ru/document/cons_doc_LAW_51057/
НК РФ ч.1: https://www.consultant.ru/document/cons_doc_LAW_19671/
НК РФ ч.2: https://www.consultant.ru/document/cons_doc_LAW_28165/
ЗК РФ: https://www.consultant.ru/document/cons_doc_LAW_33773/
ГПК РФ: https://www.consultant.ru/document/cons_doc_LAW_39570/
АПК РФ: https://www.consultant.ru/document/cons_doc_LAW_37800/
УПК РФ: https://www.consultant.ru/document/cons_doc_LAW_34481/
КАС РФ: https://www.consultant.ru/document/cons_doc_LAW_176147/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ПРАВИЛА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

— Статьи всегда в моноширном: `ст. 154 ГК РФ`
— Если вопрос затрагивает несколько кодексов — каждый разбери отдельным блоком
— При уголовных вопросах: чётко указывай санкции (срок / штраф)
— Если нужен живой адвокат — скажи прямо и объясни почему
— Короткие абзацы, пустые строки между блоками

Последняя строка каждого ответа (всегда):
⚠️ _Справочная информация, не замена консультации адвоката_"""


# ─── Rate limiting ────────────────────────────────────────────────────────────
def check_rate_limit(user_id: int) -> tuple[bool, str]:
    now = time.time()

    # Проверка блокировки
    if user_id in blocked_users:
        unblock_at = blocked_users[user_id]
        if now < unblock_at:
            remaining = int(unblock_at - now)
            m, s = remaining // 60, remaining % 60
            return False, f"🚫 Превышен лимит. Попробуйте через {m} мин {s} сек."
        else:
            del blocked_users[user_id]

    # Чистим старые метки
    window_start = now - RATE_LIMIT_WINDOW
    rate_limit_data[user_id] = [t for t in rate_limit_data[user_id] if t > window_start]

    # Проверяем лимит
    if len(rate_limit_data[user_id]) >= RATE_LIMIT_MESSAGES:
        blocked_users[user_id] = now + RATE_LIMIT_COOLDOWN
        m = RATE_LIMIT_COOLDOWN // 60
        return False, (
            f"🚫 Слишком много запросов подряд.\n"
            f"Вы заблокированы на {m} минут.\n\n"
            f"Лимит: {RATE_LIMIT_MESSAGES} сообщений за {RATE_LIMIT_WINDOW} секунд."
        )

    rate_limit_data[user_id].append(now)
    return True, ""


# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_histories[user.id] = []

    if WHITELIST and user.id not in WHITELIST:
        await update.message.reply_text("⛔ Доступ ограничен.")
        return

    keyboard = [
        [
            InlineKeyboardButton("⚖️ Трудовые споры",    callback_data="topic_labor"),
            InlineKeyboardButton("🏠 Жилищные вопросы",  callback_data="topic_housing"),
        ],
        [
            InlineKeyboardButton("👨‍👩‍👧 Семейное право",   callback_data="topic_family"),
            InlineKeyboardButton("💼 Гражданские дела",  callback_data="topic_civil"),
        ],
        [
            InlineKeyboardButton("🚔 Административка/УК", callback_data="topic_criminal"),
            InlineKeyboardButton("🏦 Налоги",             callback_data="topic_tax"),
        ],
        [InlineKeyboardButton("❓ Как пользоваться", callback_data="help")],
    ]

    await update.message.reply_text(
        f"⚖️ *Юридический советник по праву РФ*\n\n"
        f"Здравствуйте, {user.first_name}!\n\n"
        f"Я — ИИ-эксперт по всем кодексам РФ. "
        f"Задайте правовой вопрос — получите ответ со ссылками на статьи.\n\n"
        f"📋 *Выберите тему или напишите вопрос:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── /new ─────────────────────────────────────────────────────────────────────
async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_histories[update.effective_user.id] = []
    await update.message.reply_text("🔄 *Диалог сброшен.* Задайте новый вопрос.", parse_mode=ParseMode.MARKDOWN)


# ─── /help ────────────────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Как пользоваться ботом:*\n\n"
        "• Напишите вопрос обычным языком\n"
        "• Бот найдёт статьи и объяснит ситуацию\n"
        "• Можно уточнять — контекст сохраняется\n\n"
        "📌 *Примеры:*\n"
        "— Меня уволили без предупреждения\n"
        "— Сосед затопил квартиру\n"
        "— Штраф за превышение на 40 км/ч\n"
        "— Как оформить наследство\n"
        "— Работодатель не платит зарплату\n\n"
        "⚙️ *Команды:*\n"
        "/start — главное меню\n"
        "/new — новый диалог\n"
        "/stats — ваш лимит запросов\n\n"
        f"⏱ *Лимит:* {RATE_LIMIT_MESSAGES} вопросов за {RATE_LIMIT_WINDOW} сек",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /stats ───────────────────────────────────────────────────────────────────
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    now = time.time()
    recent = [t for t in rate_limit_data.get(user_id, []) if t > now - RATE_LIMIT_WINDOW]
    is_blocked = user_id in blocked_users and blocked_users[user_id] > now

    remaining_msg = ""
    if is_blocked:
        left = int(blocked_users[user_id] - now)
        remaining_msg = f"\nРазблокировка через: {left // 60} мин {left % 60} сек"

    await update.message.reply_text(
        f"📊 *Статистика:*\n\n"
        f"Запросов за {RATE_LIMIT_WINDOW}с: {len(recent)}/{RATE_LIMIT_MESSAGES}\n"
        f"Статус: {'🚫 заблокирован' + remaining_msg if is_blocked else '✅ активен'}\n"
        f"Сообщений в истории: {len(user_histories.get(user_id, []))}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Кнопки ───────────────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if WHITELIST and user_id not in WHITELIST:
        await query.message.reply_text("⛔ Доступ ограничен.")
        return

    if query.data == "help":
        await query.message.reply_text(
            "📖 Просто напишите вопрос в чат!\nИспользуйте /help для инструкции.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    topic_prompts = {
        "topic_labor":   "Расскажи кратко о 5 самых частых проблемах по Трудовому кодексу РФ, которые ты помогаешь решать.",
        "topic_housing": "Расскажи кратко о 5 самых частых жилищных вопросах по ЖК РФ, которые ты помогаешь решать.",
        "topic_family":  "Расскажи кратко о 5 самых частых вопросах семейного права по СК РФ, которые ты помогаешь решать.",
        "topic_civil":   "Расскажи кратко о 5 самых частых гражданских делах по ГК РФ, которые ты помогаешь решать.",
        "topic_criminal":"Расскажи кратко о 5 самых частых вопросах по КоАП РФ и УК РФ, которые ты помогаешь решать.",
        "topic_tax":     "Расскажи кратко о 5 самых частых налоговых вопросах по НК РФ, которые ты помогаешь решать.",
    }

    prompt = topic_prompts.get(query.data)
    if not prompt:
        return

    allowed, error_msg = check_rate_limit(user_id)
    if not allowed:
        await query.message.reply_text(error_msg)
        return

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
    response_text = await ask_claude(user_id, prompt)
    await query.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)


# ─── Обработчик сообщений ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    # Whitelist
    if WHITELIST and user_id not in WHITELIST:
        await update.message.reply_text("⛔ Доступ ограничен.")
        return

    # Длина сообщения
    if len(user_message) > MAX_MESSAGE_LENGTH:
        await update.message.reply_text(
            f"✂️ Сообщение слишком длинное ({len(user_message)} симв.).\n"
            f"Максимум — {MAX_MESSAGE_LENGTH} символов. Пожалуйста, сократите вопрос.",
        )
        return

    # Rate limit
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed:
        await update.message.reply_text(error_msg)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    response_text = await ask_claude(user_id, user_message)

    if len(response_text) > 4096:
        for chunk in split_message(response_text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.3)
    else:
        await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)


# ─── Claude API ───────────────────────────────────────────────────────────────
async def ask_claude(user_id: int, message: str) -> str:
    if user_id not in user_histories:
        user_histories[user_id] = []

    user_histories[user_id].append({"role": "user", "content": message})

    if len(user_histories[user_id]) > MAX_HISTORY:
        user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model="claude-opus-4-5",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=user_histories[user_id],
        )
        assistant_message = response.content[0].text
        user_histories[user_id].append({"role": "assistant", "content": assistant_message})
        return assistant_message

    except anthropic.RateLimitError:
        return "⏳ API временно перегружен. Подождите минуту и повторите вопрос."
    except anthropic.APIStatusError as e:
        return f"❌ Ошибка сервиса (код {e.status_code}). Попробуйте позже или /new для сброса."
    except Exception as e:
        return f"❌ Произошла ошибка: {str(e)}"


# ─── Разбивка длинных сообщений ──────────────────────────────────────────────
def split_message(text: str, max_length: int = 4096) -> list[str]:
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        pos = text.rfind("\n\n", 0, max_length)
        if pos == -1:
            pos = text.rfind("\n", 0, max_length)
        if pos == -1:
            pos = max_length
        chunks.append(text[:pos])
        text = text[pos:].lstrip()
    return chunks


# ─── Запуск ───────────────────────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("⚖️ Юридический бот запущен...")
    print(f"   Rate limit : {RATE_LIMIT_MESSAGES} сообщений / {RATE_LIMIT_WINDOW}с")
    print(f"   Cooldown   : {RATE_LIMIT_COOLDOWN}с после превышения")
    print(f"   Макс. длина: {MAX_MESSAGE_LENGTH} символов")
    print(f"   Whitelist  : {'включён' if WHITELIST else 'выключен (открыт для всех)'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
