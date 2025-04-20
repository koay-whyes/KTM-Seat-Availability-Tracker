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


# In[2]:


chromedriver_path = 'C:/chromedriver-win64/chromedriver-win64/chromedriver.exe' 

TOKEN = '7588270975:AAFkEvc-Hf_ygG1Z6BgVv-n2iLLBXgrDH6k'
chat_id = '1235697766'
message = 'null'


# In[ ]:


print("ETS/Intercity Web Scraper")
print("Please enter the following details to get started")

origin = input("Enter the origin station (IN ALL CAPS, EXACTLY THE SAME AS THE WEBSITE, NO SPACE BEHIND): ")
dest = input("Enter the destination station (IN ALL CAPS, EXACTLY THE SAME AS THE WEBSITE, NO SPACE BEHIND): ")
date = input("Enter the departure date (exp: 1 Jan 2025): ")


# In[ ]:


# Create a Service object with the path to ChromeDriver
service = Service(chromedriver_path)

# Initialize WebDriver / chrome instance - automate tab open
driver = webdriver.Chrome(service=service)
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


"""# Select the year
year_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".lightpick__select-years")))
year_dropdown.click()
year_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//option[@value='2025']")))
year_option.click()"""

# Select the month
"""
month_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".lightpick__select-months")))
month_dropdown.click()
month_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//option[@value='1']")))  
month_option.click()
desired_month = 1  
while True:
    current_month = int(
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".lightpick__select-months option[selected='selected']"))).get_attribute("value")
    )
    if current_month == desired_month:
        break

    # Switch to the iframe containing the calendar
    iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe_selector")))  # Replace with actual iframe selector
    driver.switch_to.frame(iframe)

    # Interact with the "Next" button inside the iframe
    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".lightpick__next-action")))
    next_button.click()

    # Switch back to the main page after interacting with the iframe
    driver.switch_to.default_content()
    """




# In[ ]:


"""# Desired month (0-based index; 0 = January, 1 = February, etc.)
desired_month = 1

while True:
    # Check the currently selected month
    current_month = int(
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".lightpick__select-months option[selected='selected']")
        )).get_attribute("value")
    )
    if current_month == desired_month:
        break

    try:
        # Wait for the iframe containing the calendar
        iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe_selector")))  # Replace with the actual iframe selector
        driver.switch_to.frame(iframe)  # Switch to the iframe

        # Wait for the "Next" button inside the iframe
        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".lightpick__next-action2")))
        next_button.click()
        print("Clicked the 'Next' button to navigate months.")
    except Exception as e:
        print(f"Error interacting with 'Next' button: {e}")
    finally:
        # Switch back to the main content after interacting with the iframe
        driver.switch_to.default_content()
"""
"""# Select the day
desired_day = "18"
day_element = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class, 'lightpick__day') and text()='{desired_day}' and contains(@class, 'is-available')]")))
day_element.click()"""


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


# In[ ]:


# Inefficient way to extract data
"""
train_service = []
depart = []
arrival = []
seats = []
fare = []
for row in target_table.find("tbody").find_all("tr"):
    cell = row.find_all("td")[0]  # Adjust index for the column
    train_service.append(cell.text.strip())
    cell = row.find_all("td")[1]  # Adjust index for the column
    depart.append(cell.text.strip())
    cell = row.find_all("td")[2]  # Adjust index for the column
    arrival.append(cell.text.strip())
    cell = row.find_all("td")[4]  # Adjust index for the column
    seats.append(cell.text.strip())
    cell = row.find_all("td")[5]  # Adjust index for the column
    fare.append(cell.text.strip())

print(train_service)
print(depart)
print(arrival)
print(seats)
print(fare)"""

