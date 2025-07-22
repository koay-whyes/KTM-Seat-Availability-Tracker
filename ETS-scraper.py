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

# Conversation states
ORIGIN, DESTINATION, DATE = range(3)
STATIONS = [["KL SENTRAL", "ALOR SETAR"], ["BUTTERWORTH", "IPOH"]]  # Add all stations

TOKEN = '7588270975:AAFkEvc-Hf_ygG1Z6BgVv-n2iLLBXgrDH6k'
chat_id = '1235697766'
message = 'null'

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"


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
    await update.message.reply_text(
        f"✅ Settings saved:\n"
        f"From: {context.user_data['origin']}\n"
        f"To: {context.user_data['dest']}\n"
        f"Date: {context.user_data['date']}\n\n"
        f"Starting scraping...",
        reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True)
    )
    
    # Start scraping in a separate thread
    asyncio.create_task(start_scraping(update, context))
    return ConversationHandler.END

def run_selenium(context_data, stop_event):
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless=new')  # New headless mode
    options.add_argument('--disable-gpu')
    options.add_argument('--remote-debugging-port=9222')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--window-size=1920,1080')
    
    # Explicitly set Chrome binary location
    options.binary_location = '/usr/bin/google-chrome'

    service = Service(executable_path='/usr/bin/chromedriver')
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        # Your scraping logic here using:
        origin = context_data['origin']
        dest = context_data['dest']
        date = context_data['date']

        # Example usage:
        driver.get('https://online.ktmb.com.my')
        sleep(3)
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
        origin_select = wait.until(EC.presence_of_element_located((By.ID, "select2-FromStationId-container")))

        origin_select.click()
        sleep(1)  # Allow dropdown animation

        origin_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{origin}']"))) # INPUT
        origin_option.click()





        dest_select = wait.until(EC.presence_of_element_located((By.ID, "select2-ToStationId-container")))
        dest_select.click()
        sleep(1)  # Allow dropdown animation


        dest_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{dest}']"))) #INPUT
        dest_option.click()





        depart_date = wait.until(EC.presence_of_element_located((By.ID, "OnwardDate")))
        depart_date.click()


        # Wait until the input field is present
        date_input = wait.until(EC.presence_of_element_located((By.ID, "OnwardDate")))

        # Use JavaScript to set the value of the input field
        driver.execute_script("arguments[0].value = arguments[1];", date_input, date)

        # Optional: Trigger any JavaScript events related to the field change
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", date_input)
        close_calendar = driver.find_element(By.ID,  "trainBack")
        close_calendar.click()
        depart_date = wait.until(EC.presence_of_element_located((By.ID, "OnwardDate")))
        depart_date.click()




        # Wait for the close button to be clickable
        close_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'close-date-btn') and text()='X']")))
        close_button.click()


        search_button = wait.until(EC.element_to_be_clickable((By.ID, "btnSubmit")))
        search_button.click() 
        
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
            # Wait for the table to load (adjust the timeout and conditions as needed)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "table.bottom-0"))
                )
                print("Table loaded")
            except:
                print("Table not found within the timeout period.")


            # Pass it to BeautifulSoup
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            # print(soup.prettify())

            sleep(5)
            # Locate the table
            table = soup.find_all("table", class_= "table bottom-0")
            # print(len(table))

            target_table = table[1]
            # print(target_table)

            rows = target_table.find_all('tr')
            # print(rows)

            # Extract and store in a structured format
            train_data = []
            for row in target_table.find("tbody").find_all("tr"):
                cells = row.find_all("td")
                train_data.append({
                    "train_service": cells[0].text.strip(),
                    "departure": cells[1].text.strip(),
                    "arrival": cells[2].text.strip(),
                    "seats_left": cells[4].text.strip(),
                    "fare": cells[5].text.strip()
                })

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

            def compare_data(train_data, previous_data):
                if previous_data is None:
                    return
                if train_data != previous_data:
                    print("Data has changed")
                    for i in range(len(train_data)):
                        if train_data[i]['seats_left'] < previous_data[i]['seats_left']:
                            message = '😱Seats left decreased\n' + train_data[i]['seats_left'] + ' seats left for train departing at ' + train_data[i]['departure']
                            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                            r = requests.get(url)
                        elif train_data[i]['seats_left'] > previous_data[i]['seats_left']:
                            message = '😍Seats left increased\n' + train_data[i]['seats_left'] + ' seats left for train departing at ' + train_data[i]['departure']
                            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                            r = requests.get(url)
            
            compare_data(train_data, previous_data)
            # Save the new data in memory
            previous_data = train_data
            sleep(10) 
            driver.refresh()
            
    except Exception as e:
        print(f"Selenium error: {str(e)}")
    finally:
        driver.quit()

async def start_scraping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper to run selenium in thread"""
    loop = asyncio.get_running_loop()
    stop_event = threading.Event()
    context.user_data['stop_event'] = stop_event  # Store for later access
    
    with ThreadPoolExecutor() as pool:
        await loop.run_in_executor(
            pool, 
            lambda: run_selenium(context.user_data.copy(), stop_event)
        )
    await update.message.reply_text("Scraping completed")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the bot gracefully"""
    if 'stop_event' in context.user_data:
        context.user_data['stop_event'].set()
    await update.message.reply_text("Stopping bot...")
    # This will stop the polling
    context.application.stop()
    return ConversationHandler.END

async def post_init(application: Application):
    """Set the bot commands menu after initialization"""
    await application.bot.set_my_commands([
        ("start", "Start the KTM tracker"),
        ("stop", "Stop the current tracking")
    ])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by Updates."""
    error = context.error
    if isinstance(error, Conflict):
        print("Another bot instance is already running!")
    else:
        print(f"Error: {error}")

def main():
    # Create an event to signal shutdown
    stop_event = threading.Event()
    
    try:
        message = 'Welcome to KTM Seat Availability Tracker! Please type /start to begin.'
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
        r = requests.get(url)
        
        application = ApplicationBuilder().token(TOKEN).build()

        # Register error handler
        application.add_error_handler(error_handler)

        application.add_handler(CommandHandler('stop', stop_bot))
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_origin)],
                DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_destination)],
                DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            },
            fallbacks=[CommandHandler('start', start)]
        )
        
        application.add_handler(conv_handler)
        
        # Store the application in a global variable for cleanup
        global bot_application
        bot_application = application
        
        print("Bot started. Press Ctrl+C to stop.")
        application.run_polling(stop_signals=None)  # Disable default signal handling

        
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        stop_event.set()
        if 'bot_application' in globals():
            bot_application.stop()
            bot_application.shutdown()
        print("Bot stopped successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        stop_event.set()

if __name__ == "__main__":
    main()