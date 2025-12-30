from email.mime import application
from time import sleep, strftime
from random import randint
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import smtplib
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import requests
import json
import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, ReplyKeyboardMarkup, MenuButtonCommands
from telegram.error import Conflict
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)
from webdriver_manager.chrome import ChromeDriverManager
from collections import defaultdict

import traceback
import sys

# Global dictionary to track running tasks per user
user_tasks = defaultdict(list)
user_stop_events = defaultdict(threading.Event)

# Conversation states
ORIGIN, DESTINATION, DATE = range(3)
STATIONS = [["KL SENTRAL", "ALOR SETAR"], ["BUTTERWORTH", "IPOH"]]  # Add all stations

TOKEN = '8257954942:AAHMSoyY0UPQS2QCkwyhXbM2nf2wgUIrp4c'
chat_id = '1235697766'
message = 'null'

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"

def check_heroku_environment():
    """Check if we're running on Heroku and verify environment setup"""
    is_heroku = os.environ.get('DYNO') is not None

    if not is_heroku:
        return "✅ Running locally - environment checks skipped"

    checks = []
    checks.append(f"✅ Running on Heroku (DYNO: {os.environ.get('DYNO')})")

    # Check Chrome installation
    chrome_paths = [
        '/usr/bin/google-chrome-stable',
        '/usr/bin/google-chrome',
        '/app/.chromedriver/bin/chromedriver',
        '/app/.apt/usr/bin/google-chrome'
    ]

    # Check critical dependencies
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

    # Check memory constraints
    try:
        import psutil
        memory = psutil.virtual_memory()
        checks.append(f"✅ Memory: {memory.percent}% used, {memory.available//1024//1024}MB available")

        if memory.percent > 85:
            checks.append("⚠️  High memory usage detected - consider optimizing")

    except ImportError:
        checks.append("ℹ️  psutil not available for memory monitoring")
    except Exception as e:
        checks.append(f"ℹ️  Memory check failed: {e}")

    return "\n".join(checks)

async def verify_environment():
    """Run environment checks and report to Telegram if on Heroku"""
    if os.environ.get('DYNO'):
        environment_report = check_heroku_environment()
        print(f"\n{'='*50}")
        print("Environment Check:")
        print('='*50)
        print(environment_report)
        print(f"{'='*50}\n")

async def send_to_telegram(message, chat_id=None, is_error=False):
    """Send messages to Telegram for debugging - separate error vs success"""
    try:
        if chat_id is None:
            chat_id = '1235697766'  # Your default chat ID
        
        # Truncate very long messages
        if len(message) > 4000:
            message = message[:4000] + "...[truncated]"
        
        # Add appropriate prefix
        if is_error:
            prefix = "🚨 ERROR: "
        else:
            prefix = "✅ STATUS: "
        
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={prefix}{message}"
        requests.get(url, timeout=10)
    except Exception as e:
        print(f"Failed to send message to Telegram: {e}")

# Keep the old function for backward compatibility but fix it
async def send_error_to_telegram(error_message, context=None, chat_id=None):
    """Send only error messages to Telegram"""
    await send_to_telegram(error_message, chat_id, is_error=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚂 Welcome to KTM Tracker!",
        reply_markup=ReplyKeyboardMarkup(STATIONS, one_time_keyboard=True)
    )
    await update.message.reply_text("Please select the origin station:")
    return ORIGIN

async def receive_origin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['origin'] = update.message.text.upper()
    await update.message.reply_text(
        "Please select the destination station:",
        reply_markup=ReplyKeyboardMarkup(STATIONS, one_time_keyboard=True)
    )
    return DESTINATION

async def receive_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dest'] = update.message.text.upper()
    await update.message.reply_text("Please enter the date (e.g. 30 Jul 2025):")
    return DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['date'] = update.message.text
    user_id = update.message.from_user.id
    
    await update.message.reply_text(
        f"✅ Settings saved:\n"
        f"From: {context.user_data['origin']}\n"
        f"To: {context.user_data['dest']}\n"
        f"Date: {context.user_data['date']}\n\n"
        f"Starting scraping...\n\n"
        f"Use /stop to cancel at any time.",
        reply_markup=ReplyKeyboardMarkup([["/stop"]], one_time_keyboard=True)
    )
    
    # Create a stop event for this user if it doesn't exist
    if user_id not in user_stop_events:
        user_stop_events[user_id] = threading.Event()
    else:
        # Reset the stop event if it was set previously
        user_stop_events[user_id].clear()
    
    # Start scraping in a separate task and track it
    scraping_task = asyncio.create_task(
        start_scraping(update, context, user_stop_events[user_id])
    )
    user_tasks[user_id].append(scraping_task)
    
    # Add a callback to clean up when the task is done
    scraping_task.add_done_callback(lambda t: cleanup_user_task(user_id, scraping_task))
    
    return ConversationHandler.END

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or str(user_id)
    
    if user_id in user_tasks and user_tasks[user_id]:
        # Set stop event for this user
        user_stop_events[user_id].set()
        
        # Cancel all tasks for this user
        for task in user_tasks[user_id]:
            if not task.done():
                task.cancel()
        
        # Clear the user's tasks
        user_tasks[user_id].clear()
        
        await update.message.reply_text(
            "🛑 Scraping stopped successfully. Type '/start' to start another scraping session.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "No active scraping session to stop.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )
        return ConversationHandler.END

def cleanup_user_task(user_id, task):
    """Remove completed tasks from the user's task list"""
    if user_id in user_tasks and task in user_tasks[user_id]:
        user_tasks[user_id].remove(task)
        if not user_tasks[user_id]:  # If no more tasks
            user_tasks.pop(user_id, None)
            user_stop_events.pop(user_id, None)

def run_selenium(context_data, stop_event):
    try:
        is_heroku = os.environ.get('DYNO') is not None

        if is_heroku:
            # Check resource availability before starting
            try:
                import psutil
                memory = psutil.virtual_memory()
                if memory.percent > 90:
                    print(f"High memory pressure: {memory.percent}%")
                    return None
            except:
                pass  # Skip if psutil not available
        print("=== STARTING SCRAPING SESSION ===")

        driver = None  # Initialize early to avoid UnboundLocalError
        options = Options()
        is_production = os.environ.get('DYNO') or os.environ.get('CHROME_BIN')

        if is_production:
            # Debug: Log environment variables
            chrome_env_vars = {k: v for k, v in os.environ.items() if 'CHROME' in k or 'GOOGLE' in k}
            if chrome_env_vars:
                print(f"Chrome env vars: {chrome_env_vars}")
            else:
                print("No Chrome-related env vars found")

            # Debug: Check chrome-for-testing directory
            chrome_test_dirs = [
                '/app/.chrome-for-testing',
                '/app/.chrome-for-testing/chrome-linux64',
                '/app/.chrome',
                '/app/.chromedriver'
            ]
            for dir_path in chrome_test_dirs:
                try:
                    if os.path.exists(dir_path):
                        files = os.listdir(dir_path)
                        print(f"✅ Found {dir_path}: {files[:5]}")
                except Exception as e:
                    pass

            # Check for chrome binary specifically
            possible_chrome_bins = [
                '/app/.chrome-for-testing/chrome-linux64/chrome',
                '/app/.chrome-for-testing/chrome',
                '/app/.chrome/chrome',
            ]
            for chrome_bin in possible_chrome_bins:
                if os.path.exists(chrome_bin):
                    print(f"✅ Found Chrome binary: {chrome_bin}")

            # Find Chrome binary from known locations
            chrome_paths = [
                os.environ.get('CHROME_BIN'),  # Check environment variable first
                os.environ.get('GOOGLE_CHROME_BIN'),  # Alternative env var
                os.environ.get('GOOGLE_CHROME_SHIM'),  # Old buildpack
                '/app/.chrome-for-testing/chrome-linux64/chrome',  # chrome-for-testing buildpack
                '/app/.chrome-for-testing/chrome',  # chrome-for-testing alt path
                '/app/.chrome/chrome',  # Alternative location
                '/app/.apt/usr/bin/google-chrome',  # Heroku apt buildpack
                '/usr/bin/google-chrome',  # Standard location
                '/usr/bin/google-chrome-stable',  # Alternative standard location
            ]

            chrome_binary = None
            for path in chrome_paths:
                if path and os.path.exists(path):
                    chrome_binary = path
                    if is_heroku:
                        print(f"✅ Found Chrome at: {path}")
                    break

            if chrome_binary:
                options.binary_location = chrome_binary
            else:
                error_msg = "❌ Chrome binary not found in any expected location"
                if is_heroku:
                    print(error_msg)
                raise Exception(error_msg)

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--single-process')

        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')

        max_retries = 3
        retry_count = 0

        # ChromeDriver initialization with detailed error handling
        while retry_count < max_retries and not stop_event.is_set():
            try:
                if is_heroku and retry_count > 0:
                    print(f"Retry {retry_count}/{max_retries}")

                # Use ChromeDriver from chrome-for-testing buildpack if available
                chromedriver_paths = [
                    '/app/.chrome-for-testing/chromedriver-linux64/chromedriver',  # chrome-for-testing buildpack
                    os.environ.get('CHROMEDRIVER_PATH'),  # Environment variable
                ]

                chromedriver_path = None
                for path in chromedriver_paths:
                    if path and os.path.exists(path):
                        chromedriver_path = path
                        if is_heroku:
                            print(f"✅ Using ChromeDriver: {path}")
                        break

                if chromedriver_path:
                    # Use the matching ChromeDriver from buildpack
                    service = Service(chromedriver_path)
                else:
                    # Fall back to ChromeDriverManager (for local development)
                    if is_heroku:
                        print("Using ChromeDriverManager (fallback)")
                    service = Service(ChromeDriverManager().install())

                driver = webdriver.Chrome(service=service, options=options)
                driver.set_page_load_timeout(120)
                driver.implicitly_wait(60)

                if is_heroku:
                    print("✅ ChromeDriver initialized on Heroku")
                break

            except Exception as e:
                retry_count += 1
                error_msg = f"ChromeDriver init attempt {retry_count}: {str(e)}"

                if is_heroku:
                    print(error_msg)

                if retry_count >= max_retries:
                    if is_heroku:
                        print("❌ ChromeDriver failed after all retries")
                    raise Exception(f"Failed to initialize ChromeDriver after {max_retries} attempts: {e}")

                sleep(5) 

        if driver is None or stop_event.is_set():
            if is_heroku:
                asyncio.run(send_to_telegram("Scraping cancelled before starting", is_error=False))
            return None
        try:
            # Your scraping logic here using:
            origin = context_data['origin']
            dest = context_data['dest']
            date = context_data['date']

            # Check if stop was requested before starting
            if stop_event.is_set():
                print("Stop requested before starting scraping")
                return None

            try:
                driver.get('https://online.ktmb.com.my')
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                # asyncio.run(send_to_telegram("Page loaded successfully", is_error=False))
            except Exception as e:
                raise Exception(f"Failed to load page: {e}")

            # Check for stop request
            if stop_event.is_set():
                print("Stop requested during initial page load")
                return None
            
            # Define XPath
            xp_popup_close = '//button[contains(@class, "btn payment-modal-btn")]'

            # Find all matching elements
            popup_buttons = driver.find_elements(By.XPATH, xp_popup_close)

            # Close ad button (Website popup)
            # Access the specific button (index 3 for the fourth button)
            # try:
            #     specific_button = popup_buttons[3]  # 4th button
            #     specific_button.click() 
            # except IndexError:
            #     print("Button at the specified index not found.")
            # except Exception as e:
            #     print("An error occurred:", e)
            
            # Select an origin station (example: KL Sentral)
            wait = WebDriverWait(driver, 10)

            try:
                origin_select = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "select2-FromStationId-container"))
                )
                origin_select.click()
                sleep(1)
                
                origin_option = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{origin}']"))
                )
                origin_option.click()
                # asyncio.run(send_to_telegram("Origin selected", is_error=False))
            except Exception as e:
                raise Exception(f"Failed to select origin '{origin}': {e}")


            # Check for stop request
            if stop_event.is_set():
                print("Stop requested after origin selection")
                return None

            try:
                dest_select = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "select2-ToStationId-container"))
                )
                dest_select.click()
                sleep(1)
                
                dest_option = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{dest}']"))
                )
                dest_option.click()
                # asyncio.run(send_to_telegram("Destination selected", is_error=False))
            except Exception as e:
                raise Exception(f"Failed to select destination '{dest}': {e}")

            # Check for stop request
            if stop_event.is_set():
                print("Stop requested after destination selection")
                return None

            try:
                depart_date = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "OnwardDate"))
                )
                depart_date.click()
                
                date_input = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "OnwardDate"))
                )
                driver.execute_script("arguments[0].value = arguments[1];", date_input, date)

                # Optional: Trigger any JavaScript events related to the field change
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", date_input)
                close_calendar = driver.find_element(By.ID,  "trainBack")
                close_calendar.click()
                depart_date = wait.until(EC.presence_of_element_located((By.ID, "OnwardDate")))
                depart_date.click()                
                close_button = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'close-date-btn') and text()='X']"))
                )
                close_button.click()
                # asyncio.run(send_to_telegram("Date set", is_error=False))
            except Exception as e:
                raise Exception(f"Failed to set date '{date}': {e}")

            # Check for stop request
            if stop_event.is_set():
                print("Stop requested after date selection")
                return None

            try:
                search_button = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.ID, "btnSubmit"))
                )
                search_button.click()
                # asyncio.run(send_to_telegram("Search initiated", is_error=False))
            except Exception as e:
                raise Exception(f"Failed to click search button: {e}") 

            # Check for stop request
            if stop_event.is_set():
                print("Stop requested after search")
                return None
            
            TEST_MODE = False  # Set to False in production

            if TEST_MODE:
                previous_data = [{'train_service': 'Platinum - 9272', 'departure': '07:20', 'arrival': '12:02', 'seats_left': '999', 'fare': 'MYR 102.00'},
                                {'train_service': 'Platinum - 9274', 'departure': '09:55', 'arrival': '14:37', 'seats_left': '999', 'fare': 'MYR 102.00'},
                                {'train_service': 'Gold - 9420', 'departure': '10:41', 'arrival': '15:36', 'seats_left': '0', 'fare': 'MYR 74.00'},
                                {'train_service': 'Express - 9206', 'departure': '18:00', 'arrival': '22:14', 'seats_left': '0', 'fare': 'MYR 114.00'},
                                {'train_service': 'Platinum - 9278', 'departure': '22:50', 'arrival': '03:32\n                                        +1', 'seats_left': '999', 'fare': 'MYR 99.00'}]
            else:
                previous_data = None  # Initialize previous_data to None for production

            while not stop_event.is_set():
                # Check for stop request at the beginning of each iteration
                if stop_event.is_set():
                    print("Stop requested at start of loop iteration")
                    break

                # Wait for the table to load (adjust the timeout and conditions as needed)
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "table.bottom-0"))
                    )
                    print("Table loaded")
                except:
                    print("Table not found within the timeout period.")
                    # Check if we should continue or break
                    if stop_event.is_set():
                        break
                    continue

                # Check for stop request
                if stop_event.is_set():
                    print("Stop requested after table load")
                    break


                # Pass it to BeautifulSoup
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                # print(soup.prettify())
                if stop_event.is_set():
                    print("Stop requested during parsing")
                    break

                sleep(10)
                # Locate the table
                table = soup.find_all("table", class_= "table bottom-0")
                # print(len(table))

                            
                if not table or len(table) < 2:
                    print("Table not found in HTML")
                    if stop_event.is_set():
                        break
                    sleep(5)
                    continue

                target_table = table[1]
                # print(target_table)

                rows = target_table.find_all('tr')
                # print(rows)

                # Extract and store in a structured format
                train_data = []
                try:
                    tbody = target_table.find("tbody")
                    if not tbody:
                        print("No tbody found in table")
                        if stop_event.is_set():
                            break
                        sleep(5)
                        continue
                    
                    for row in target_table.find("tbody").find_all("tr"):
                        cells = row.find_all("td")
                        train_data.append({
                            "train_service": cells[0].text.strip(),
                            "departure": cells[1].text.strip(),
                            "arrival": cells[2].text.strip(),
                            "seats_left": cells[4].text.strip(),
                            "fare": cells[5].text.strip()
                        })
                except Exception as e:
                    print(f"Error parsing table: {e}")
                    if stop_event.is_set():
                        break
                    sleep(5)
                    continue
                
                # Check for stop request
                if stop_event.is_set():
                    print("Stop requested after data extraction")
                    break

                # Print structured data
                for train in train_data:
                    print(train)
                    # Send data to Telegram for first scrape only
                    if previous_data is None:
                        message = f"🚆 Train Service: {train['train_service']}\n" \
                                f"🕒 Departure: {train['departure']}\n" \
                                f"🕒 Arrival: {train['arrival']}\n" \
                                f"💺 Seats Left: {train['seats_left']}\n" \
                                f"💰 Fare: {train['fare']}"
                        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                        r = requests.get(url)
                if previous_data is None:
                    message = f"Now checking for changes in seats left for {origin} to {dest} on {date}..."
                    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                    r = requests.get(url)
                
                # file_name = f"train_data_{origin}_to_{dest}_{date}.json"
                # file_path = os.path.join(os.getcwd(), file_name)
                
                # # compare and notify

                # if os.path.exists(file_path):
                #     # Load previous data
                #     with open(file_path, "r") as file:
                #         previous_data = json.load(file)
                    
                #     # Compare new data with previous data
                #     if train_data != previous_data:
                #         print("Data has changed")
                #         for i in range(len(train_data)):
                #             if train_data[i]['seats_left'] != previous_data[i]['seats_left']:
                #                 message = 'Seats number changed for ' + train_data[i]['train_service'] + ' departing at ' + train_data[i]['departure']
                #                 url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                #                 r = requests.get(url)
                #                 print(r.json())
                            
                #         # Save the new data
                #         with open(file_path, "w") as file:
                #             json.dump(train_data, file, indent=4)
                #     else:
                #         print("No changes detected")
                # else:
                #     # File doesn't exist; save new data
                #     with open(file_path, "w") as file:
                #         json.dump(train_data, file, indent=4)
                #     print("Data saved for the first time")
                def compare_data(train_data, previous_data, TOKEN, chat_id):
                    """Compare current data with previous data and send notifications for changes"""
                    if previous_data is None:
                        return
                        
                    if train_data != previous_data:
                        print("Data has changed")
                        # Make sure we're comparing the same trains
                        min_length = min(len(train_data), len(previous_data))
                        
                        for i in range(min_length):
                            try:
                                # Extract numeric values from seat strings (e.g., "10" from "10 seats")
                                current_seats = ''.join(filter(str.isdigit, train_data[i]['seats_left']))
                                previous_seats = ''.join(filter(str.isdigit, previous_data[i]['seats_left']))
                                
                                current_seats = int(current_seats) if current_seats else 0
                                previous_seats = int(previous_seats) if previous_seats else 0
                                
                                if current_seats < previous_seats:
                                    message = f'😱 Seats left decreased\n{current_seats} seats left for {train_data[i]["train_service"]} departing at {train_data[i]["departure"]}'
                                    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                                    requests.get(url, timeout=5)
                                elif current_seats > previous_seats:
                                    message = f'😍 Seats left increased\n{current_seats} seats left for {train_data[i]["train_service"]} departing at {train_data[i]["departure"]}'
                                    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                                    requests.get(url, timeout=5)
                            except Exception as e:
                                print(f"Error comparing train data: {e}")

                compare_data(train_data, previous_data, TOKEN, chat_id)
                # Save the new data in memory
                previous_data = train_data
                if stop_event.is_set():
                    print("Stop requested before refresh")
                    break

                # Wait with periodic stop checks instead of a long sleep
                for _ in range(20):  # Check every 0.5 seconds for 10 seconds total
                    if stop_event.is_set():
                        print("Stop requested during wait")
                        break
                    sleep(0.5)
                
                if stop_event.is_set():
                    break

                sleep(10) 
                driver.refresh()
            print("Scraping loop ended")
            return {"status": "completed", "data": previous_data} if previous_data else {"status": "stopped"}            
                # Main scraping logic with detailed error handling
            return perform_scraping(driver, context_data, stop_event)
        
        except Exception as e:
            print(f"Selenium error: {str(e)}")
        finally:
            driver.quit()
            
    except Exception as e:
        error_msg = f"run_selenium failed: {str(e)}\nTraceback: {traceback.format_exc()}"
        asyncio.run(send_error_to_telegram(error_msg))
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                asyncio.run(send_error_to_telegram(f"Error quitting driver: {e}"))        

async def start_scraping(update: Update, context: ContextTypes.DEFAULT_TYPE, stop_event: threading.Event):
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    is_heroku = os.environ.get('DYNO') is not None

    try:
        if is_heroku:
            await context.bot.send_message(chat_id=chat_id, text="🔄 Starting scraping on Heroku...")
            # Run environment verification
            await verify_environment()
        else:
            await context.bot.send_message(chat_id=chat_id, text="🔄 Starting scraping process...")

        # Adjust timeout based on environment
        timeout = 600 if is_heroku else 300  # 10 minutes for Heroku, 5 for local

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: run_selenium(context.user_data, stop_event)),
            timeout=timeout
        )

        if stop_event.is_set():
            await context.bot.send_message(chat_id=chat_id, text="⏹️ Scraping cancelled by user")
            return

        if result is None:
            error_msg = "Scraping returned no results - likely failed during execution"
            if is_heroku:
                await send_error_to_telegram(error_msg, chat_id=chat_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Scraping failed - no results obtained")
        else:
            await process_and_send_results(update, context, result)

    except asyncio.TimeoutError:
        error_msg = f"Scraping timed out after {'10' if is_heroku else '5'} minutes"
        if is_heroku:
            await send_error_to_telegram(error_msg, chat_id=chat_id)
        await context.bot.send_message(chat_id=chat_id, text="⏰ Scraping timed out")

    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=chat_id, text="⏹️ Scraping cancelled")

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        if is_heroku:
            await send_error_to_telegram(error_msg, chat_id=chat_id)
            await send_error_to_telegram(f"Traceback: {traceback.format_exc()}", chat_id=chat_id)
        await context.bot.send_message(chat_id=chat_id, text="❌ Unexpected error during scraping")

    finally:
        cleanup_user_task(user_id, asyncio.current_task())

# async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Stop the bot gracefully"""
#     if 'stop_event' in context.user_data:
#         context.user_data['stop_event'].set()
#     await update.message.reply_text("Stopping bot...")
#     # This will stop the polling
#     context.application.stop()
#     return ConversationHandler.END

async def post_init(application: Application):
    """Set the bot commands menu after initialization"""
    await application.bot.set_my_commands([
        ("start", "Start the KTM tracker"),
        ("stop", "Stop the current tracking")
    ])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates."""
    error = context.error
    if isinstance(error, Conflict):
        print("Another bot instance is already running!")
    else:
        print(f"Error: {error}")

async def process_and_send_results(update, context, result):
    if result:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Scraping completed! Results: {result}",
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="No results found or scraping was cancelled.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
        )

def main():
    try:
        message = 'Welcome to KTM Seat Availability Tracker! Please type /start to begin.'
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
        r = requests.get(url)
        
        application = ApplicationBuilder().token(TOKEN).build()

        # Register error handler
        application.add_error_handler(error_handler)
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_origin)],
                DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_destination)],
                DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            },
            fallbacks=[CommandHandler('stop', stop)]  # Add stop as fallback
        )

        application.add_handler(CommandHandler("stop", stop))
        application.add_handler(conv_handler)
        
        print("Bot started. Press Ctrl+C to stop.")
        application.run_polling()
        
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        print("Bot stopped successfully.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()