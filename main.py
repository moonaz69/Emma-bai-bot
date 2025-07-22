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

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Временная зона Баку
BAKU_TZ = pytz.timezone("Asia/Baku")


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой личный ассистент. /help — список команд.")


# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/remind HH:MM текст — напоминать каждый день\n"
        "/schedule YYYY-MM-DD HH:MM текст — напоминать один раз\n"
        "/calc выражение — вычислить\n"
        "Просто напиши текст — отвечу через AI."
    )


# Команда /calc
async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = update.message.text.partition(" ")[2]
    try:
        result = eval(expr, {"__builtins__": {}})
        await update.message.reply_text(f"Результат: {result}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка вычисления: {e}")


# Callback для всех напоминаний
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, job.data)


# Команда /remind — ежедневное напоминание
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Формат: /remind HH:MM текст
    _, time_str, text = update.message.text.split(" ", 2)
    hh, mm = map(int, time_str.split(":"))
    job_time = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
    context.job_queue.run_daily(
        reminder_callback,
        time=job_time,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"daily_{update.effective_chat.id}_{hh}_{mm}",
    )
    await update.message.reply_text(f"Напоминание установлено каждый день в {time_str} (Baku time)")


# Команда /schedule — одноразовое напоминание
async def schedule_once(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Формат: /schedule YYYY-MM-DD HH:MM текст
    _, date_str, time_str, text = update.message.text.split(" ", 3)
    dt_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    dt = BAKU_TZ.localize(dt_naive)
    context.job_queue.run_once(
        reminder_callback,
        when=dt,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"once_{update.effective_chat.id}_{int(dt.timestamp())}",
    )
    await update.message.reply_text(f"Запланировано на {date_str} {time_str} (Baku time)")


# Все остальные текстовые сообщения — через OpenAI
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
    )
    answer = resp.choices[0].message.content
    await update.message.reply_text(answer)


if __name__ == "__main__":
    # Инициализация бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("schedule", schedule_once))

    # Обработчик для всего прочего
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    # Запуск бота (job_queue стартует автоматически вместе с run_polling)
    app.run_polling()
