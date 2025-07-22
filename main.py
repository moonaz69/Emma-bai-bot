import os
import sys
import logging
import json
from datetime import datetime, time
import pytz
import openai
from typing import List, Dict

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ─── Configuration ───────────────────────────────────────────────────────────
STORE_FILE = 'reminders.json'
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Load tokens ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN is not set! Exiting.")
    sys.exit(1)
logger.info("✅ TELEGRAM_TOKEN loaded")

# ─── Timezone ──────────────────────────────────────────────────────────────────
BAKU_TZ = pytz.timezone("Asia/Baku")

# ─── Conversation states ───────────────────────────────────────────────────────
(MENU, REMIND_TIME, REMIND_TEXT,
 AFTER_TIME, AFTER_TEXT,
 NOTE_TEXT, MANAGE_SELECT) = range(7)

# ─── Persistence Helpers ───────────────────────────────────────────────────────
def load_store() -> Dict[str, List[Dict]]:
    if os.path.exists(STORE_FILE):
        with open(STORE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_store(store: Dict[str, List[Dict]]):
    with open(STORE_FILE, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

# ─── Scheduling from store at startup ─────────────────────────────────────────
def schedule_from_store(app):
    store = load_store()
    for chat_key, items in store.items():
        chat_id = int(chat_key)
        for item in items:
            try:
                name = item['name']
                if item['type'] == 'daily':
                    hh, mm = map(int, item['time'].split(':'))
                    jt = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
                    app.job_queue.run_daily(
                        reminder_callback, time=jt,
                        chat_id=chat_id, data=item['text'], name=name
                    )
                elif item['type'] == 'after':
                    when = float(item['when'])
                    app.job_queue.run_once(
                        reminder_callback, when=when,
                        chat_id=chat_id, data=item['text'], name=name
                    )
            except Exception as e:
                logger.error(f"Failed to schedule stored job {item}: {e}")

# ─── Callback when a reminder is triggered ────────────────────────────────────
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, job.data)

# ─── List and manage reminders ─────────────────────────────────────────────────
async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = load_store()
    chat_key = str(update.effective_chat.id)
    items = store.get(chat_key, [])
    if not items:
        await update.message.reply_text("У тебя нет запланированных напоминаний.")
        return ConversationHandler.END
    lines = []
    for idx, item in enumerate(items, start=1):
        if item['type'] == 'daily':
            lines.append(f"{idx}) daily @ {item['time']} — {item['text']}")
        else:
            rt = datetime.fromtimestamp(item['when'], BAKU_TZ).strftime('%Y-%m-%d %H:%M:%S')
            lines.append(f"{idx}) once @ {rt} — {item['text']}")
    context.user_data['store_jobs'] = items
    keyboard = [[str(i)] for i in range(1, len(items)+1)]
    keyboard.append(["/cancel"])
    await update.message.reply_text(
        "Выбери номер для удаления или /cancel:\n" + "\n".join(lines),
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return MANAGE_SELECT

async def delete_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sel = update.message.text
    if sel == '/cancel':
        await update.message.reply_text("Операция отменена.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    try:
        idx = int(sel) - 1
        items = context.user_data.get('store_jobs', [])
        item = items.pop(idx)
        job = context.job_queue.get_job(item['name'])
        if job:
            job.remove()
        store = load_store()
        store[str(update.effective_chat.id)] = [it for it in store.get(str(update.effective_chat.id), []) if it['name'] != item['name']]
        save_store(store)
        await update.message.reply_text("Напоминание удалено.", reply_markup=ReplyKeyboardRemove())
    except Exception:
        await update.message.reply_text("Некорректный выбор.")
        return MANAGE_SELECT
    return ConversationHandler.END

# ─── Direct command handlers with persistence ─────────────────────────────────
async def remind_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 2)
    if len(parts) < 3:
        return await update.message.reply_text("Используй /remind HH:MM текст")
    time_str, text = parts[1], parts[2]
    try:
        hh, mm = map(int, time_str.split(':'))
        name = f"daily_{update.effective_chat.id}_{hh}_{mm}"
        jt = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
        context.job_queue.run_daily(reminder_callback, time=jt, chat_id=update.effective_chat.id, data=text, name=name)
        store = load_store()
        store.setdefault(str(update.effective_chat.id), []).append({'name': name, 'type': 'daily', 'time': time_str, 'text': text})
        save_store(store)
        await update.message.reply_text(f"Ежедневно в {time_str}: {text}")
    except Exception:
        await update.message.reply_text("Неверный формат. /remind HH:MM текст")

async def after_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(' ', 3)
    if len(parts) < 4 or parts[1] != 'after':
        return await update.message.reply_text("Используй /remind after N текст")
    try:
        sec = int(parts[2])
        text = parts[3]
        name = f"after_{update.effective_chat.id}_{int(datetime.now().timestamp())}"
        context.job_queue.run_once(reminder_callback, when=sec, chat_id=update.effective_chat.id, data=text, name=name)
        store = load_store()
        store.setdefault(str(update.effective_chat.id), []).append({'name': name, 'type': 'after', 'when': datetime.now().timestamp()+sec, 'text': text})
        save_store(store)
        await update.message.reply_text(f"Через {sec} сек: {text}")
    except Exception:
        await update.message.reply_text("Неверный формат. /remind after N текст")

# ─── Menu conversation handlers ────────────────────────────────────────────────
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Установить напоминание"],
        ["Напомнить через"],
        ["Показать напоминания"],
        ["Составить заметку"],
    ]
    await update.message.reply_text(
        "Выберите опцию:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return MENU

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Установить напоминание":
        await update.message.reply_text("Во сколько? (HH:MM)", reply_markup=ReplyKeyboardRemove())
        return REMIND_TIME
    if text == "Напомнить через":
        await update.message.reply_text("Сколько секунд?", reply_markup=ReplyKeyboardRemove())
        return AFTER_TIME
    if text == "Показать напоминания":
        return await list_reminders(update, context)
    if text == "Составить заметку":
        await update.message.reply_text("Что записать?", reply_markup=ReplyKeyboardRemove())
        return NOTE_TEXT
    await update.message.reply_text("Пожалуйста, выберите опцию.")
    return MENU

async def remind_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['menu_time'] = update.message.text
    await update.message.reply_text(f"Текст напоминания для {update.message.text}")
    return REMIND_TEXT

async def remind_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = context.user_data.pop('menu_time')
    text = update.message.text
    hh, mm = map(int, time_str.split(':'))
    name = f"daily_{update.effective_chat.id}_{hh}_{mm}"
    jt = time(hour=hh, minute=mm, tzinfo=BAKU_TZ)
    context.job_queue.run_daily(reminder_callback, time=jt, chat_id=update.effective_chat.id, data=text, name=name)
    store = load_store()
    store.setdefault(str(update.effective_chat.id), []).append({'name': name,'type':'daily','time':time_str,'text':text})
    save_store(store)
    await update.message.reply_text(f"Ежедневно в {time_str}: {text}")
    return ConversationHandler.END

async def after_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['after_duration'] = update.message.text
    await update.message.reply_text("Текст напоминания?")
    return AFTER_TEXT

async def after_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dur = context.user_data.pop('after_duration')
    text = update.message.text
    try:
        sec = int(dur)
    except:
        return await update.message.reply_text("Неверный формат секунд")
    name = f"after_{update.effective_chat.id}_{int(datetime.now().timestamp())}"
    context.job_queue.run_once(reminder_callback, when=sec, chat_id=update.effective_chat.id, data=text, name=name)
    store = load_store()
    store.setdefault(str(update.effective_chat.id), []).append({'name': name,'type':'after','when': datetime.now().timestamp()+sec,'text':text})
    save_store(store)
    await update.message.reply_text(f"Через {sec} сек: {text}")
    return ConversationHandler.END

async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text
    await update.message.reply_text(f"Заметка сохранена: {note}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Меню отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{'role':'user','content':update.message.text}])
    await update.message.reply_text(resp.choices[0].message.content)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # schedule stored jobs
    schedule_from_store(app)

    # Direct commands
    app.add_handler(CommandHandler('remind', remind_direct))
    app.add_handler(CommandHandler('remind after', after_direct))
    app.add_handler(CommandHandler('reminders', list_reminders))

    # Menu conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler('menu', menu)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
            REMIND_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_time)],
            REMIND_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_text)],
            AFTER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, after_time)],
            AFTER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, after_text)],
            NOTE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, note_text)],
            MANAGE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_selected)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv)

    # AI fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_response))

    # start polling
    app.run_polling()
