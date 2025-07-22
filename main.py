import os
import logging
from datetime import datetime
import pytz
import openai

from telegram import Update, Voice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройка логов
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# Планировщик задач
scheduler = AsyncIOScheduler(timezone=pytz.UTC)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный ассистент. /help — список команд."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/remind HH:MM текст — напомнить каждый день в это время\n"
        "/schedule YYYY-MM-DD HH:MM текст — однократно в дату и время\n"
        "/calc <выражение> — вычислить математически\n"
        "Просто отправь текст — я отвечу с помощью AI."
    )


async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = update.message.text.partition(" ")[2]
    try:
        result = eval(expr, {"__builtins__": {}})
        await update.message.reply_text(f"Результат: {result}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка вычисления: {e}")


def schedule_reminder(chat_id: int, text: str):
    async def job():
        await app.bot.send_message(chat_id, text)

    return job


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /remind 09:00 Пить лекарство
    args = update.message.text.split(" ", 2)
    time_str, text = args[1], args[2]
    hour, minute = map(int, time_str.split(":"))
    # Добавляем в планировщик ежедневное напоминание
    scheduler.add_job(
        schedule_reminder(update.effective_chat.id, text),
        trigger="cron",
        hour=hour,
        minute=minute,
        id=f"remind_{update.effective_chat.id}_{hour}_{minute}",
        replace_existing=True,
    )
    await update.message.reply_text(f"Напоминание установлено: каждый день в {time_str}")


async def schedule_once(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /schedule 2025-07-25 15:30 Встреча
    args = update.message.text.split(" ", 3)
    date_str, time_str, text = args[1], args[2], args[3]
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    dt = pytz.UTC.localize(dt)
    scheduler.add_job(
        schedule_reminder(update.effective_chat.id, text),
        trigger="date",
        run_date=dt,
    )
    await update.message.reply_text(f"Запланировано на {date_str} {time_str}")


async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}]
    )
    text = resp.choices[0].message.content
    await update.message.reply_text(text)


if __name__ == "__main__":
    # Инициализируем бота
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("schedule", schedule_once))
    # Всё, что не команда — идёт в AI
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    # Запускаем планировщик и бота
    scheduler.start()
    app.run_polling()

