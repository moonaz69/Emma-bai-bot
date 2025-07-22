import os
import logging
from datetime import datetime, time
import pytz
import openai
import sys

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверка токенов
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN is not set! The bot cannot start.")
    sys.exit(1)
logger.info(f"✅ TELEGRAM_TOKEN loaded ({len(TELEGRAM_TOKEN)} chars)")
openai.api_key = OPENAI_API_KEY

BAKU_TZ = pytz.timezone("Asia/Baku")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой личный ассистент.")

# … тут остальные хендлеры (help, time, remind, calc…)

if __name__ == "__main__":
    logger.info("🔄 Initializing ApplicationBuilder")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Регистрируем только /start для теста
    app.add_handler(CommandHandler("start", start))

    logger.info("▶️ Running bot polling")
    app.run_polling()
