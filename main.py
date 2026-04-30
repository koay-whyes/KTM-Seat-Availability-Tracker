from __future__ import annotations

import asyncio
import os
import threading
import traceback
from collections import defaultdict
from datetime import date, datetime

import requests
from dotenv import load_dotenv
from telegram import MenuButtonCommands, ReplyKeyboardMarkup, Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from scraper import run_selenium


user_tasks = defaultdict(list)
user_stop_events = defaultdict(threading.Event)
user_selection_events = defaultdict(threading.Event)
user_selected_services = defaultdict(list)
user_available_trains = {}

ORIGIN, DESTINATION, DATE = range(3)
STATIONS = [["BDR TASEK SELATAN", "KL SENTRAL"], ["KUALA LUMPUR", "SUNGAI BULOH"], ["RAWANG", "TANJUNG MALIM"], 
            ["KAMPAR", "BATU GAJAH"], ["IPOH","KUALA KANGSAR"],["TAIPING","BUKIT MERTAJAM"], ["SUNGAI PETANI", "GURUN"], 
            ["ALOR SETAR", "ARAU"], ["PADANG BESAR"]]

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_DEFAULT_CHAT_ID")


def check_heroku_environment():
    """Check if we're running on Heroku and verify environment setup."""
    is_heroku = os.environ.get('DYNO') is not None

    if not is_heroku:
        return "✅ Running locally - environment checks skipped"

    checks = []
    checks.append(f"✅ Running on Heroku (DYNO: {os.environ.get('DYNO')})")

    dependencies = [
        ('/usr/bin/wget', 'wget'),
        ('/usr/bin/curl', 'curl'),
        ('/usr/bin/unzip', 'unzip')
    ]

    for path, name in dependencies:
        if os.path.exists(path):
            checks.append(f"✅ {name} found")
        else:
            checks.append(f"❌ {name} not found")

    try:
        import psutil

        memory = psutil.virtual_memory()
        checks.append(f"✅ Memory: {memory.percent}% used, {memory.available//1024//1024}MB available")
        if memory.percent > 85:
            checks.append("⚠️  High memory usage detected - consider optimizing")
    except ImportError:
        checks.append("ℹ️  psutil not available for memory monitoring")
    except Exception as error:
        checks.append(f"ℹ️  Memory check failed: {error}")

    return "\n".join(checks)


async def verify_environment():
    """Run environment checks and report to Telegram if on Heroku."""
    if os.environ.get('DYNO'):
        environment_report = check_heroku_environment()
        print(f"\n{'='*50}")
        print('Environment Check:')
        print('='*50)
        print(environment_report)
        print(f"{'='*50}\n")


async def send_to_telegram(message, chat_id=None, is_error=False):
    """Send messages to Telegram for debugging - separate error vs success."""
    try:
        if chat_id is None:
            chat_id = DEFAULT_CHAT_ID

        if not chat_id:
            print('Telegram message skipped: TELEGRAM_DEFAULT_CHAT_ID is not set')
            return

        if len(message) > 4000:
            message = message[:4000] + '...[truncated]'

        prefix = '🚨 ERROR: ' if is_error else '✅ STATUS: '
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={prefix}{message}"
        requests.get(url, timeout=10)
    except Exception as error:
        print(f"Failed to send message to Telegram: {error}")


async def send_error_to_telegram(error_message, context=None, chat_id=None):
    """Send only error messages to Telegram."""
    await send_to_telegram(error_message, chat_id, is_error=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🚂 Welcome to KTM Tracker!',
        reply_markup=ReplyKeyboardMarkup(STATIONS, one_time_keyboard=True)
    )
    await update.message.reply_text('Please select the origin station:')
    return ORIGIN


async def receive_origin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['origin'] = update.message.text.upper()
    await update.message.reply_text(
        'Please select the destination station:',
        reply_markup=ReplyKeyboardMarkup(STATIONS, one_time_keyboard=True)
    )
    return DESTINATION


async def receive_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dest'] = update.message.text.upper()
    await update.message.reply_text('Please enter the date (e.g. 30 Jul 2025):')
    return DATE


async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['date'] = update.message.text

    parsed_date = datetime.strptime(context.user_data['date'], '%d %b %Y').date()
    if parsed_date < date.today():
        await update.message.reply_text('❌ The date cannot be in the past. Please enter a valid date (e.g. 30 Jul 2025):')
        return DATE

    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    context.user_data['user_id'] = user_id
    context.user_data['chat_id'] = chat_id
    user_selection_events[user_id].clear()
    user_selected_services[user_id].clear()
    user_available_trains.pop(user_id, None)

    await update.message.reply_text(
        f"✅ Settings saved:\n"
        f"From: {context.user_data['origin']}\n"
        f"To: {context.user_data['dest']}\n"
        f"Date: {context.user_data['date']}\n\n"
        f"Starting scraping...\n\n"
        f"Use /stop to cancel at any time.",
        reply_markup=ReplyKeyboardMarkup([["/stop"]], one_time_keyboard=True)
    )

    if user_id not in user_stop_events:
        user_stop_events[user_id] = threading.Event()
    else:
        user_stop_events[user_id].clear()

    scraping_task = asyncio.create_task(start_scraping(update, context, user_stop_events[user_id]))
    user_tasks[user_id].append(scraping_task)
    scraping_task.add_done_callback(lambda task: cleanup_user_task(user_id, scraping_task))

    return ConversationHandler.END


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    has_active_session = user_id in user_stop_events and not user_stop_events[user_id].is_set()
    has_tasks = user_id in user_tasks and user_tasks[user_id]

    if has_active_session or has_tasks:
        if user_id in user_stop_events:
            user_stop_events[user_id].set()

        if user_id in user_tasks:
            for task in user_tasks[user_id]:
                if not task.done():
                    task.cancel()
            user_tasks[user_id].clear()

        if user_id in user_selection_events:
            user_selection_events[user_id].set()

        await update.message.reply_text(
            "🛑 Scraping stopped successfully. Type '/start' to start another scraping session.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )
        return ConversationHandler.END

    await update.message.reply_text(
        'No active scraping session to stop.',
        reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
    )
    return ConversationHandler.END


def cleanup_user_task(user_id, task):
    """Remove completed tasks from the user's task list."""
    if user_id in user_tasks and task in user_tasks[user_id]:
        user_tasks[user_id].remove(task)
        if not user_tasks[user_id]:
            user_tasks.pop(user_id, None)
            user_selection_events.pop(user_id, None)
            user_selected_services.pop(user_id, None)
            user_available_trains.pop(user_id, None)


async def handle_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's choice of train services to monitor."""
    user_id = update.message.from_user.id

    if user_id not in user_available_trains:
        await update.message.reply_text('No active train list. Use /start to begin a new search.')
        return

    raw = update.message.text
    try:
        indices = [int(part.strip()) for part in raw.split(',') if part.strip().isdigit()]
    except Exception:
        indices = []

    available = user_available_trains.get(user_id, [])
    chosen_services = []
    for index in indices:
        if 1 <= index <= len(available):
            chosen_services.append(available[index - 1]['train_service'])

    seen = set()
    chosen_services = [service for service in chosen_services if not (service in seen or seen.add(service))]

    if not chosen_services:
        await update.message.reply_text('Please send numbers from the list, separated by commas (e.g. 1,3,5).')
        return

    user_selected_services[user_id] = chosen_services
    user_selection_events[user_id].set()

    await update.message.reply_text('🔔 Got it! Tracking these services:\n' + '\n'.join(chosen_services))


async def start_scraping(update: Update, context: ContextTypes.DEFAULT_TYPE, stop_event: threading.Event):
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    is_heroku = os.environ.get('DYNO') is not None

    try:
        if is_heroku:
            await context.bot.send_message(chat_id=chat_id, text='🔄 Starting scraping on Heroku...')
            await verify_environment()
        else:
            await context.bot.send_message(chat_id=chat_id, text='🔄 Starting scraping process...')

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_selenium(
                context.user_data,
                stop_event,
                user_selected_services,
                user_selection_events,
                user_available_trains,
                TOKEN,
                DEFAULT_CHAT_ID,
            )
        )

        if stop_event.is_set():
            await context.bot.send_message(chat_id=chat_id, text='⏹️ Scraping cancelled by user')
            return

        if result is None:
            error_msg = 'Scraping returned no results - likely failed during execution'
            if is_heroku:
                await send_error_to_telegram(error_msg, chat_id=chat_id)
            await context.bot.send_message(chat_id=chat_id, text='❌ Scraping failed - no results obtained')
        else:
            await process_and_send_results(update, context, result)

    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=chat_id, text='⏹️ Scraping cancelled')
    except Exception as error:
        error_msg = f'Unexpected error: {str(error)}'
        if is_heroku:
            await send_error_to_telegram(error_msg, chat_id=chat_id)
            await send_error_to_telegram(f'Traceback: {traceback.format_exc()}', chat_id=chat_id)
        await context.bot.send_message(chat_id=chat_id, text='❌ Unexpected error during scraping')
    finally:
        cleanup_user_task(user_id, asyncio.current_task())
        if stop_event.is_set():
            user_stop_events.pop(user_id, None)


async def post_init(application: Application):
    """Set the bot commands menu after initialization."""
    await application.bot.set_my_commands([
        ('start', 'Start the KTM tracker'),
        ('stop', 'Stop the current tracking')
    ])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates."""
    error = context.error
    if isinstance(error, Conflict):
        print('Another bot instance is already running!')
    else:
        print(f'Error: {error}')
        traceback.print_exc()


async def process_and_send_results(update, context, result):
    if result:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Scraping completed! Results: {result}',
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='No results found or scraping was cancelled.',
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )


def main():
    try:
        if not TOKEN:
            raise RuntimeError('Missing TELEGRAM_BOT_TOKEN environment variable')

        if DEFAULT_CHAT_ID:
            message = 'Welcome to KTM Seat Availability Tracker! Please type /start to begin.'
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={DEFAULT_CHAT_ID}&text={message}"
            requests.get(url, timeout=10)

        application = ApplicationBuilder().token(TOKEN).build()
        application.add_error_handler(error_handler)

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_origin)],
                DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_destination)],
                DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            },
            fallbacks=[CommandHandler('stop', stop)]
        )

        application.add_handler(CommandHandler('stop', stop))
        application.add_handler(MessageHandler(filters.Regex(r'^\d+(\s*,\s*\d+)*$'), handle_service_selection))
        application.add_handler(conv_handler)

        print('Bot started. Press Ctrl+C to stop.')
        application.run_polling(allowed_updates=None)
    except KeyboardInterrupt:
        print('\nShutting down gracefully...')
        print('Bot stopped successfully.')
    except Exception as error:
        print(f'Error: {error}')


if __name__ == '__main__':
    main()