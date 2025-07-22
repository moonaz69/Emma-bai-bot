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
logger = logging.getLogger(__name__)

# Токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Часовой пояс Баку
BAKU_TZ = pytz.timezone("Asia/Baku")


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой личный ассистент. /help — список команд.")


# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/time — показать текущее время (системное, UTC, Baku)\n"
        "/remind HH:MM текст — напоминать каждый день\n"
        "/remind after N second текст — через N секунд\n"
        "/schedule YYYY-MM-DD HH:MM текст — один раз в дату/время\n"
        "/calc выражение — вычислить\n"
        "Просто напиши текст — отвечу через AI."
    )


# /time
async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_system = datetime.now()  # системное (без tzinfo)
    now_utc = datetime.now(pytz.UTC)
    now_baku = now_utc.astimezone(BAKU_TZ)
    reply = (
        f"🕒 System time: {now_system.strftime('%Y-%m-%d %H:%M:%S')} ({now_system.tzinfo})\n"
        f"🕒 UTC       : {now_utc.strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n"
        f"🕒 Baku time : {now_baku.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Baku)"
    )
    await update.message.reply_text(reply)


# /calc
async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = update.message.text.partition(" ")[2]
    try:
        result = eval(expr, {"__builtins__": {}})
        await update.message.reply_text(f"Результат: {result}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка вычисления: {e}")


# общий callback для напоминаний
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, job.data)


# /remind
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(" ", 4)
    if len(parts) >= 4 and parts[1].lower() == "after":
        # после N секунд
        try:
            seconds = int(parts[2])
            text = parts[3] if len(parts) == 4 else parts[4]
        except ValueError:
            return await update.message.reply_text(
                "Используй /remind after <секунд> <текст>"
            )
        context.job_queue.run_once(
            reminder_callback,
            when=seconds,
            chat_id=update.effective_chat.id,
            data=text,
            name=f"after_{update.effective_chat.id}_{int(datetime.now().timestamp())}",
        )
        return await update.message.reply_text(
            f"Напоминание через {seconds} секунд установлено: «{text}»"
        )

    # ежедневное в HH:MM
    try:
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
        return await update.message.reply_text(
            f"Ежедневное напоминание в {time_str} (Baku time)"
        )
    except Exception:
        return await update.message.reply_text(
            "Неправильный формат. /remind HH:MM <текст> или /remind after <секунд> <текст>"
        )


# /schedule — разово
async def schedule_once(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(
        f"Запланировано на {date_str} {time_str} (Baku time)"
    )


# AI-ответы
async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}]
    )
    await update.message.reply_text(resp.choices[0].message.content)


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # регистрируем команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("schedule", schedule_once))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))
