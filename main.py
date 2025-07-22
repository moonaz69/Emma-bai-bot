import os
import logging
from datetime import datetime, time
import pytz
import openai

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Логи
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Хендлеры
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой личный ассистент. /help — команды.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/remind HH:MM текст — напоминать каждый день\n"
        "/schedule YYYY-MM-DD HH:MM текст — напоминать один раз\n"
        "/calc выражение — вычислить\n"
        "Текст без / — через AI."
    )

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = update.message.text.partition(" ")[2]
    try:
        result = eval(expr, {"__builtins__": {}})
        await update.message.reply_text(f"Результат: {result}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка вычисления: {e}")

# Общий callback для напоминания
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, job.data)

# Ежедневное напоминание
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, time_str, text = update.message.text.split(" ", 2)
    hh, mm = map(int, time_str.split(":"))
    # время с таймзоной UTC; при необходимости поменяйте на вашу
    job_time = time(hour=hh, minute=mm, tzinfo=pytz.UTC)
    context.job_queue.run_daily(
        reminder_callback,
        time=job_time,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"daily_{update.effective_chat.id}_{hh}_{mm}",
    )
    await update.message.reply_text(f"Напоминание установлено каждый день в {time_str}")

# Однократное напоминание
async def schedule_once(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, date_str, time_str, text = update.message.text.split(" ", 3)
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    dt = pytz.UTC.localize(dt)
    context.job_queue.run_once(
        reminder_callback,
        when=dt,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"once_{update.effective_chat.id}_{dt.timestamp()}",
    )
    await update.message.reply_text(f"Запланировано на {date_str} {time_str}")

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
    )
    await update.message.reply_text(resp.choices[0].message.content)

# Точка входа
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("schedule", schedule_once))

    # Всё остальное — AI
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    # Запускаем бота (job_queue стартует автоматически)
    app.run_polling()
