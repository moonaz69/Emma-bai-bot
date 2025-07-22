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
from gdrive import upload_file_local

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Load token & Drive folder ID ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN is not set! Exiting.")
    sys.exit(1)
if not DRIVE_FOLDER_ID:
    logger.error("❌ DRIVE_FOLDER_ID is not set! Exiting.")
    sys.exit(1)

# ─── Conversation states ───────────────────────────────────────────────────────
MENU, REMIND_DELAY, REMIND_TEXT = range(3)

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный ассистент. Используй /menu для настройки напоминания."
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Напоминания"]]
    await update.message.reply_text(
        "Выберите опцию:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return MENU

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Напоминания":
        await update.message.reply_text(
            "Через какое время напомнить? Введите задержку HH:MM:SS", 
            reply_markup=ReplyKeyboardRemove()
        )
        return REMIND_DELAY
    await update.message.reply_text("Пожалуйста, выберите пункт меню.")
    return MENU

async def remind_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        h, m, s = map(int, text.split(':'))
        delay = h * 3600 + m * 60 + s
    except Exception:
        await update.message.reply_text(
            "❌ Неверный формат. Введите HH:MM:SS, например 01:00:00 для часа."
        )
        return REMIND_DELAY

    context.user_data['delay'] = delay
    await update.message.reply_text("Введите текст напоминания:")
    return REMIND_TEXT

async def remind_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    delay = context.user_data.get('delay', 0)
    # Планируем одно напоминание
    job_name = f"remind_{update.effective_chat.id}_{int(datetime.now().timestamp())}"
    context.job_queue.run_once(
        reminder_callback,
        when=delay,
        chat_id=update.effective_chat.id,
        data=text,
        name=job_name,
    )
    # Запись в локальный файл
    h = delay // 3600
    m = (delay % 3600) // 60
    s = delay % 60
    log_line = f"{datetime.now().isoformat()} | {h:02d}:{m:02d}:{s:02d} | {text}\n"
    with open("reminders.txt", "a", encoding="utf-8") as f:
        f.write(log_line)
    # Загрузка в Google Drive
    try:
        res = upload_file_local("reminders.txt", DRIVE_FOLDER_ID)
        link = res.get('webViewLink')
    except Exception as e:
        link = f"Ошибка загрузки: {e}"
    # Ответ пользователю
    await update.message.reply_text(
        f"✅ Напоминание через {h:02d}:{m:02d}:{s:02d} установлено: {text}\n"
        f"Файл списка напоминаний: {link}"
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

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

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
