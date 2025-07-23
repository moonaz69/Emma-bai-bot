import os
import sys
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

import openai
from gdrive import upload_file_bytes  # <-- импорт для Google Drive

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Load tokens & keys ────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
DRIVE_FOLDER_ID  = os.getenv("DRIVE_FOLDER_ID")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN is not set! Exiting.")
    sys.exit(1)
if not DRIVE_FOLDER_ID:
    logger.error("❌ DRIVE_FOLDER_ID is not set! Exiting.")
    sys.exit(1)
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY is not set! Exiting.")
    sys.exit(1)

openai.api_key = OPENAI_API_KEY

# ─── Conversation states ───────────────────────────────────────────────────────
MENU, REMIND_DELAY, REMIND_TEXT = range(3)

# ─── Helpers ───────────────────────────────────────────────────────────────────
def save_reminders_list(chat_id: int, reminders: list[str]) -> str:
    """
    Собирает список строк reminders и заливает его в файл
    reminders_<chat_id>.txt на Google Drive. Возвращает webViewLink.
    """
    content = "\n".join(reminders).encode("utf-8")
    filename = f"reminders_{chat_id}.txt"
    meta = upload_file_bytes(filename, content)
    return meta.get("webViewLink", "— без ссылки —")

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный ассистент. Используй /menu для настройки напоминания."
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Напоминания"], ["Мои напоминания"], ["/cancel"]]
    await update.message.reply_text(
        "Выберите опцию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return MENU

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Напоминания":
        await update.message.reply_text(
            "Через какое время напомнить? Введите задержку в формате HH:MM:SS",
            reply_markup=ReplyKeyboardRemove()
        )
        return REMIND_DELAY

    if text == "Мои напоминания":
        jobs = context.chat_data.get("jobs", [])
        if not jobs:
            await update.message.reply_text("У вас нет активных напоминаний.")
        else:
            lines = [f"{j['time']} — {j['text']}" for j in jobs]
            link = save_reminders_list(update.effective_chat.id, lines)
            await update.message.reply_text(f"Список напоминаний сохранён:\n{link}")
        return ConversationHandler.END

    await update.message.reply_text("Пожалуйста, выберите пункт меню.")
    return MENU

async def remind_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        h, m, s = map(int, text.split(":"))
        delay = h * 3600 + m * 60 + s
    except Exception:
        await update.message.reply_text(
            "❌ Неверный формат. Введите HH:MM:SS, например 01:00:00 для часа."
        )
        return REMIND_DELAY

    context.user_data["delay"] = delay
    await update.message.reply_text("Введите текст напоминания:")
    return REMIND_TEXT

async def remind_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    delay = context.user_data.get("delay", 0)

    # сохраняем в chat_data для «Мои напоминания»
    job_record = {
        "time": str(datetime.now().time().replace(microsecond=0)),
        "text": text,
        "delay": delay
    }
    context.chat_data.setdefault("jobs", []).append(job_record)

    # планируем напоминание
    context.job_queue.run_once(
        reminder_callback,
        when=delay,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"remind_{update.effective_chat.id}_{int(datetime.now().timestamp())}",
    )

    h = delay // 3600
    m = (delay % 3600) // 60
    s = delay % 60
    await update.message.reply_text(
        f"✅ Напоминание через {h:02d}:{m:02d}:{s:02d} установлено: {text}"
    )
    return ConversationHandler.END

async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, f"🔔 Напоминание: {job.data}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Операция отменена.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ─── ChatGPT-обработчик ────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.partition(" ")[2].strip()
    if not prompt:
        await update.message.reply_text("❌ Пиши так: /chat <твой вопрос>")
        return

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user", "content": prompt}]
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        answer = f"Ошибка OpenAI: {e}"

    await update.message.reply_text(answer)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # существующие хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chat", chat))        # <-- новый

    conv = ConversationHandler(
        entry_points=[CommandHandler("menu", menu)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
            REMIND_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_delay)],
            REMIND_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)

    app.run_polling()
