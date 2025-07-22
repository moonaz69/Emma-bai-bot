import os
import sys
import logging
from datetime import datetime, time
import pytz
import openai
from typing import List

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
logger.info("✅ TELEGRAM_TOKEN loaded")

openai.api_key = OPENAI_API_KEY

# ─── Timezone ──────────────────────────────────────────────────────────────────
BAKU_TZ = pytz.timezone("Asia/Baku")

# ─── Conversation states ───────────────────────────────────────────────────────
MENU, REMIND_TIME, REMIND_TEXT, CALL_TIME, CALL_TEXT, NOTE_TEXT, MANAGE_SELECT = range(7)

# ─── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой личный ассистент.\n/help — список команд.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/menu — открыть меню опций\n"
        "/time — текущее время\n"
        "/calc — вычислить (введите `/calc 2+2`)\n"
        "/reminders — показать список напоминаний\n"
        "или просто отправьте текст для AI-ответа"
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

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.get_jobs()
    lines: List[str] = []
    user_jobs = []
    for job in jobs:
        if job.chat_id != update.effective_chat.id:
            continue
        if not job.next_run_time:
            continue
        next_local = job.next_run_time.astimezone(BAKU_TZ)
        lines.append(f"{len(user_jobs)+1}) {job.name} — {next_local.strftime('%Y-%m-%d %H:%M:%S')}")
        user_jobs.append(job)
    if not lines:
        await update.message.reply_text("У тебя нет запланированных напоминаний.")
    else:
        # Сохраним список в user_data
        context.user_data['jobs'] = user_jobs
        keyboard = [[str(i)] for i in range(1, len(user_jobs)+1)]
        keyboard.append(["/cancel"])
        await update.message.reply_text(
            "Выбери номер напоминания для удаления:\n" + "\n".join(lines),
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return MANAGE_SELECT
    return ConversationHandler.END

# ─── Menu conversation ──────────────────────────────────────────────────────────
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Установить напоминание"],
        ["Перезвонить по аудиозвонку"],
        ["Составить заметку"],
        ["Показать напоминания"],
    ]
    await update.message.reply_text(
        "Выберите опцию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return MENU

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "Установить напоминание":
        await update.message.reply_text("Во сколько напомнить? (HH:MM)", reply_markup=ReplyKeyboardRemove())
        return REMIND_TIME
    if choice == "Перезвонить по аудиозвонку":
        await update.message.reply_text("Во сколько перезвонить? (HH:MM)", reply_markup=ReplyKeyboardRemove())
        return CALL_TIME
    if choice == "Составить заметку":
        await update.message.reply_text("Что записать в заметку?", reply_markup=ReplyKeyboardRemove())
        return NOTE_TEXT
    if choice == "Показать напоминания":
        return await list_reminders(update, context)
    await update.message.reply_text("Пожалуйста, выберите одну из опций.")
    return MENU

async def remind_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text
    context.user_data["menu_time"] = time_str
    await update.message.reply_text(f"Напиши текст напоминания для {time_str}")
    return REMIND_TEXT

async def remind_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    time_str = context.user_data.get("menu_time")
    hh, mm = map(int, time_str.split(":"))
    jt = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
    context.job_queue.run_daily(
        reminder_callback,
        time=jt,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"menu_daily_{update.effective_chat.id}_{hh}_{mm}" 
    )
    await update.message.reply_text(f"Ежедневное напоминание в {time_str}: {text}")
    return ConversationHandler.END

async def call_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text
    context.user_data["call_time"] = time_str
    await update.message.reply_text(f"Напиши текст для звонка в {time_str}")
    return CALL_TEXT

async def call_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    time_str = context.user_data.get("call_time")
    hh, mm = map(int, time_str.split(":"))
    jt = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
    context.job_queue.run_daily(
        reminder_callback,
        time=jt,
        chat_id=update.effective_chat.id,
        data=f"📞 Звонок: {text}",
        name=f"menu_call_{update.effective_chat.id}_{hh}_{mm}" 
    )
    await update.message.reply_text(f"Аудиозвонок запланирован в {time_str}: {text}")
    return ConversationHandler.END

async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    await update.message.reply_text(f"Заметка сохранена:\n{note}")
    return ConversationHandler.END

async def manage_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sel = update.message.text
    if sel == "/cancel":
        await update.message.reply_text("Операция отменена.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    try:
        idx = int(sel) - 1
        jobs: List = context.user_data.get('jobs', [])
        job = jobs[idx]
        job.remove()
        await update.message.reply_text(f"Напоминание удалено.", reply_markup=ReplyKeyboardRemove())
    except Exception:
        await update.message.reply_text("Некорректный выбор. Попробуй ещё раз или /cancel.")
        return MANAGE_SELECT
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Меню отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    await update.message.reply_text(resp.choices[0].message.content)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("reminders", list_reminders))

    # ConversationHandler для /menu
    conv = ConversationHandler(
        entry_points=[CommandHandler("menu", menu)],
        states={
            MENU:       [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
            REMIND_TIME:[MessageHandler(filters.TEXT & ~filters.COMMAND, remind_time)],
            REMIND_TEXT:[MessageHandler(filters.TEXT & ~filters.COMMAND, remind_text)],
            CALL_TIME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, call_time)],
            CALL_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, call_text)],
            NOTE_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, note_text)],
            MANAGE_SELECT:[MessageHandler(filters.TEXT & ~filters.COMMAND, manage_select)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)

    # Всё остальное — AI
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    # Запуск
    app.run_polling()
