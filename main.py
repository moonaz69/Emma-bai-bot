import os
import sys
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
logger.info(f"✅ TELEGRAM_TOKEN loaded ({len(TELEGRAM_TOKEN)} chars)")

openai.api_key = OPENAI_API_KEY  # пустой ключ ещё не критичен

# ─── Timezones ─────────────────────────────────────────────────────────────────
BAKU_TZ = pytz.timezone("Asia/Baku")

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой личный ассистент.\n"
        "/help — список команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/time — текущее время (системное, UTC, Baku)\n"
        "/remind HH:MM текст — ежедневное напоминание (Baku)\n"
        "/remind after N second текст — напоминание через N секунд\n"
        "/schedule YYYY-MM-DD HH:MM текст — разовое напоминание\n"
        "/calc выражение — вычислить\n"
        "любой другой текст — ответ AI"
    )

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_sys = datetime.now()
    now_utc = datetime.now(pytz.UTC)
    now_baku = now_utc.astimezone(BAKU_TZ)
    await update.message.reply_text(
        f"🕒 System: {now_sys.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🕒 UTC   : {now_utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🕒 Baku  : {now_baku.strftime('%Y-%m-%d %H:%M:%S')}"
    )

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = update.message.text.partition(" ")[2]
    try:
        result = eval(expr, {"__builtins__": {}})
        await update.message.reply_text(f"Результат: {result}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка вычисления: {e}")

async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, job.data)

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(" ", 4)
    if len(parts) >= 4 and parts[1].lower() == "after":
        # /remind after N second текст
        try:
            sec = int(parts[2])
        except ValueError:
            return await update.message.reply_text(
                "Неверно. /remind after <секунд> <текст>"
            )
        text = parts[3] if len(parts) == 4 else parts[4]
        context.job_queue.run_once(
            reminder_callback,
            when=sec,
            chat_id=update.effective_chat.id,
            data=text,
            name=f"after_{update.effective_chat.id}_{int(datetime.now().timestamp())}"
        )
        return await update.message.reply_text(
            f"Напоминание через {sec} сек установлено: «{text}»"
        )

    # /remind HH:MM текст
    try:
        _, tstr, text = update.message.text.split(" ", 2)
        hh, mm = map(int, tstr.split(":"))
        jt = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
        context.job_queue.run_daily(
            reminder_callback,
            time=jt,
            chat_id=update.effective_chat.id,
            data=text,
            name=f"daily_{update.effective_chat.id}_{hh}_{mm}"
        )
        await update.message.reply_text(
            f"Ежедневное напоминание в {tstr} (Baku)"
        )
    except Exception:
        await update.message.reply_text(
            "Неверный формат. /remind HH:MM <текст> или /remind after <секунд> <текст>"
        )

async def schedule_once(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /schedule YYYY-MM-DD HH:MM текст
    try:
        _, dstr, tstr, text = update.message.text.split(" ", 3)
        dt_naive = datetime.strptime(f"{dstr} {tstr}", "%Y-%m-%d %H:%M")
        dt = BAKU_TZ.localize(dt_naive)
    except Exception:
        return await update.message.reply_text(
            "Неверный формат. /schedule YYYY-MM-DD HH:MM <текст>"
        )

    context.job_queue.run_once(
        reminder_callback,
        when=dt,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"once_{update.effective_chat.id}_{int(dt.timestamp())}"
    )
    await update.message.reply_text(
        f"Запланировано: {dstr} {tstr} (Baku)"
    )

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    await update.message.reply_text(resp.choices[0].message.content)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🔄 Init ApplicationBuilder")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("schedule", schedule_once))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    logger.info("▶️ Starting polling")
    app.run_polling()
