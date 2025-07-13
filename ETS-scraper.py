#!/usr/bin/env python
# coding: utf-8

# In[1]:


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
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)
from webdriver_manager.chrome import ChromeDriverManager

# In[2]:
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

# parameters for ChromeDriver(chromedriver_path, options=options)
driver = webdriver.Chrome(service=webdriver.ChromeService(ChromeDriverManager().install()), options=options)

TOKEN = '7588270975:AAFkEvc-Hf_ygG1Z6BgVv-n2iLLBXgrDH6k'
chat_id = '1235697766'
message = 'null'


# In[ ]:

message = 'Welcome to ETS/Intercity Web Scraper! \n\n***************************************** \nPlease enter the following details to get started :)'
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
r = requests.get(url)
print(r.json())

# origin = input("Enter the origin station (IN ALL CAPS, EXACTLY THE SAME AS THE WEBSITE, NO SPACE BEHIND): ")
# dest = input("Enter the destination station (IN ALL CAPS, EXACTLY THE SAME AS THE WEBSITE, NO SPACE BEHIND): ")
# date = input("Enter the departure date (exp: 1 Jan 2025): ")
origin = "KL SENTRAL"
dest = "ALOR SETAR"
date = "30 Jul 2025"

sleep(2)


# In[ ]:


ktmb = 'https://online.ktmb.com.my'
driver.get(ktmb)
sleep(3)


# In[ ]:


# Define XPath
xp_popup_close = '//button[contains(@class, "btn payment-modal-btn")]'

# Find all matching elements
popup_buttons = driver.find_elements(By.XPATH, xp_popup_close)

# Access the specific button (index 3 for the fourth button)
try:
    specific_button = popup_buttons[3]  # 4th button
    specific_button.click() 
except IndexError:
    print("Button at the specified index not found.")
except Exception as e:
    print("An error occurred:", e)


# In[ ]:


# Select an origin station (example: KL Sentral)
wait = WebDriverWait(driver, 10)
origin_select = wait.until(EC.presence_of_element_located((By.ID, "select2-FromStationId-container")))

origin_select.click()
sleep(1)  # Allow dropdown animation

origin_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{origin}']"))) # INPUT
origin_option.click()


# In[ ]:


dest_select = wait.until(EC.presence_of_element_located((By.ID, "select2-ToStationId-container")))
dest_select.click()
sleep(1)  # Allow dropdown animation


dest_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{dest}']"))) #INPUT
dest_option.click()


# In[ ]:


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

# In[ ]:


# Wait for the close button to be clickable
close_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'close-date-btn') and text()='X']")))
close_button.click()


# In[ ]:


search_button = wait.until(EC.element_to_be_clickable((By.ID, "btnSubmit")))
search_button.click()


# In[ ]:


while True:
    
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
    
    file_name = f"train_data_{origin}_to_{dest}_{date}.json"
    file_path = os.path.join(os.getcwd(), file_name)
    
    # compare and notify

    if os.path.exists(file_path):
        # Load previous data
        with open(file_path, "r") as file:
            previous_data = json.load(file)
        
        # Compare new data with previous data
        if train_data != previous_data:
            print("Data has changed")
            for i in range(len(train_data)):
                if train_data[i]['seats_left'] != previous_data[i]['seats_left']:
                    message = 'Seats number changed for ' + train_data[i]['train_service'] + ' departing at ' + train_data[i]['departure']
                    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={message}"
                    r = requests.get(url)
                    print(r.json())
                
            # Save the new data
            with open(file_path, "w") as file:
                json.dump(train_data, file, indent=4)
        else:
            print("No changes detected")
    else:
        # File doesn't exist; save new data
        with open(file_path, "w") as file:
            json.dump(train_data, file, indent=4)
        print("Data saved for the first time")
    
    sleep(10)
    driver.refresh()