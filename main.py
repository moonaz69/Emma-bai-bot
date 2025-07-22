import os
import sys
import logging
from datetime import datetime, timedelta
import pytz
import openai

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Load tokens ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN is not set! Exiting.")
    sys.exit(1)
openai.api_key = OPENAI_API_KEY

# ─── Timezone ──────────────────────────────────────────────────────────────────
BAKU_TZ = pytz.timezone("Asia/Baku")

# ─── Conversation states ───────────────────────────────────────────────────────
MENU, CALL_DELAY = range(2)

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный ассистент. Используй /menu для начала."
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Перезвонить по аудио"]]
    await update.message.reply_text(
        "Выберите опцию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return MENU

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "Перезвонить по аудио":
        await update.message.reply_text(
            "Через сколько напомнить? Введите MM:SS", reply_markup=ReplyKeyboardRemove()
        )
        return CALL_DELAY
    await update.message.reply_text("Пожалуйста, выберите опцию из меню.")
    return MENU

async def schedule_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        parts = text.split(':')
        minutes = int(parts[0])
        seconds = int(parts[1]) if len(parts) > 1 else 0
n        delay = minutes * 60 + seconds
    except Exception:
        await update.message.reply_text(
            "Неверный формат. Используй MM:SS, например 01:00 для одной минуты."
        )
        return CALL_DELAY
    # Schedule job
    context.job_queue.run_once(
        callback_call,
        when=delay,
        chat_id=update.effective_chat.id,
        name=f"call_{update.effective_chat.id}_{int(datetime.now().timestamp())}"
    )
    await update.message.reply_text(f"Запланирован звонок через {minutes:02d}:{seconds:02d}.")
    return ConversationHandler.END

async def callback_call(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    # Simulate audio call by sending a voice message or text
    await context.bot.send_message(chat_id, "📞 Звоню вам (имитация аудиозвонка)...")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Меню отменено.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("menu", menu)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
            CALL_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_call)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    app.run_polling()
