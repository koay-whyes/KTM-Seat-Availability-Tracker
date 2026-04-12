from __future__ import annotations

import os
from time import sleep

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from analytics import build_analytics_summary
from storage import ensure_snapshot_table, get_database_connection, save_scrape_snapshot


def compare_data(train_data, previous_data, selected_services, token, chat_id):
    """Compare current data with previous data and send notifications for changes."""
    if previous_data is None:
        return

    if train_data != previous_data:
        print("Data has changed")
        current_by_service = {train['train_service']: train for train in train_data}
        previous_by_service = {train['train_service']: train for train in previous_data}
        services_to_check = selected_services if selected_services else list(current_by_service.keys())
        print(f"Services to check: {services_to_check}")

        for service_name in services_to_check:
            try:
                if service_name not in current_by_service or service_name not in previous_by_service:
                    continue

                current_entry = current_by_service[service_name]
                previous_entry = previous_by_service[service_name]
                current_seats = ''.join(filter(str.isdigit, current_entry['seats_left']))
                previous_seats = ''.join(filter(str.isdigit, previous_entry['seats_left']))

                current_seats = int(current_seats) if current_seats else 0
                previous_seats = int(previous_seats) if previous_seats else 0

                if current_seats < previous_seats:
                    message = f'😱 Seats left decreased\n{current_seats} seats left for {service_name} departing at {current_entry["departure"]}'
                    requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={message}", timeout=5)
                elif current_seats > previous_seats:
                    message = f'😍 Seats left increased\n{current_seats} seats left for {service_name} departing at {current_entry["departure"]}'
                    requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={message}", timeout=5)
            except Exception as error:
                print(f"Error comparing train data: {error}")


def run_selenium(
    context_data,
    stop_event,
    user_selected_services,
    user_selection_events,
    user_available_trains,
    token,
    default_chat_id,
):
    is_heroku = os.environ.get('DYNO') is not None
    user_id = context_data.get('user_id')
    chat_id = context_data.get('chat_id') or default_chat_id
    db_connection = None

    if is_heroku:
        try:
            import psutil

            memory = psutil.virtual_memory()
            if memory.percent > 90:
                print(f"High memory pressure: {memory.percent}%")
                return None
        except Exception:
            pass

    print("=== STARTING SCRAPING SESSION ===")
    driver = None
    options = Options()
    is_production = os.environ.get('DYNO') or os.environ.get('CHROME_BIN')

    db_connection = get_database_connection()
    if db_connection is not None:
        ensure_snapshot_table(db_connection)

    if is_production:
        chrome_paths = [
            os.environ.get('CHROME_BIN'),
            os.environ.get('GOOGLE_CHROME_BIN'),
            os.environ.get('GOOGLE_CHROME_SHIM'),
            '/app/.chrome-for-testing/chrome-linux64/chrome',
            '/app/.chrome-for-testing/chrome',
            '/app/.chrome/chrome',
            '/app/.apt/usr/bin/google-chrome',
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
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

    while retry_count < max_retries and not stop_event.is_set():
        try:
            chromedriver_paths = [
                '/app/.chrome-for-testing/chromedriver-linux64/chromedriver',
                os.environ.get('CHROMEDRIVER_PATH'),
            ]

            chromedriver_path = None
            for path in chromedriver_paths:
                if path and os.path.exists(path):
                    chromedriver_path = path
                    if is_heroku:
                        print(f"✅ Using ChromeDriver: {path}")
                    break

            if chromedriver_path:
                service = Service(chromedriver_path)
            else:
                if is_heroku:
                    print("Using ChromeDriverManager (fallback)")
                service = Service(ChromeDriverManager().install())

            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(120)
            driver.implicitly_wait(60)
            break

        except Exception as error:
            retry_count += 1
            print(f"ChromeDriver init attempt {retry_count}: {error}")
            if retry_count >= max_retries:
                raise Exception(f"Failed to initialize ChromeDriver after {max_retries} attempts: {error}")
            sleep(5)

    if driver is None or stop_event.is_set():
        return None

    try:
        origin = context_data['origin']
        dest = context_data['dest']
        date = context_data['date']

        if stop_event.is_set():
            print("Stop requested before starting scraping")
            return None

        driver.get('https://online.ktmb.com.my')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

        if stop_event.is_set():
            print("Stop requested during initial page load")
            return None

        wait = WebDriverWait(driver, 10)

        origin_select = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'select2-FromStationId-container'))
        )
        origin_select.click()
        sleep(1)
        origin_option = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{origin}']"))
        )
        origin_option.click()

        if stop_event.is_set():
            print("Stop requested after origin selection")
            return None

        dest_select = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'select2-ToStationId-container'))
        )
        dest_select.click()
        sleep(1)
        dest_option = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[@class='station-name' and text()='{dest}']"))
        )
        dest_option.click()

        if stop_event.is_set():
            print("Stop requested after destination selection")
            return None

        depart_date = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'OnwardDate'))
        )
        depart_date.click()
        date_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, 'OnwardDate'))
        )
        driver.execute_script('arguments[0].value = arguments[1];', date_input, date)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", date_input)
        driver.find_element(By.ID, 'trainBack').click()
        depart_date = wait.until(EC.presence_of_element_located((By.ID, 'OnwardDate')))
        depart_date.click()
        close_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'close-date-btn') and text()='X']"))
        )
        close_button.click()

        if stop_event.is_set():
            print("Stop requested after date selection")
            return None

        search_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, 'btnSubmit')))
        search_button.click()

        if stop_event.is_set():
            print("Stop requested after search")
            return None

        previous_data = None

        while not stop_event.is_set():
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'table.bottom-0')))
                print('Table loaded')
            except Exception:
                print('Table not found within the timeout period.')
                if stop_event.is_set():
                    break
                continue

            if stop_event.is_set():
                print('Stop requested after table load')
                break

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            if stop_event.is_set():
                print('Stop requested during parsing')
                break

            sleep(10)
            tables = soup.find_all('table', class_='table bottom-0')
            if not tables or len(tables) < 2:
                print('Table not found in HTML')
                if stop_event.is_set():
                    break
                sleep(5)
                continue

            target_table = tables[1]
            train_data = []
            try:
                tbody = target_table.find('tbody')
                if not tbody:
                    print('No tbody found in table')
                    if stop_event.is_set():
                        break
                    sleep(5)
                    continue

                for row in tbody.find_all('tr'):
                    cells = row.find_all('td')
                    train_data.append({
                        'train_service': cells[0].text.strip(),
                        'departure': cells[1].text.strip(),
                        'arrival': cells[2].text.strip(),
                        'seats_left': cells[4].text.strip(),
                        'fare': cells[5].text.strip(),
                    })
            except Exception as error:
                print(f'Error parsing table: {error}')
                if stop_event.is_set():
                    break
                sleep(5)
                continue

            if stop_event.is_set():
                print('Stop requested after data extraction')
                break

            selected_services = user_selected_services.get(user_id, [])
            save_scrape_snapshot(
                db_connection,
                context_data,
                train_data,
                previous_data,
                selected_services,
            )

            for train in train_data:
                print(train)

            if previous_data is None:
                user_available_trains[user_id] = train_data
                options_lines = []
                for index, train in enumerate(train_data, start=1):
                    options_lines.append(
                        f"{index}) {train['train_service']} | Dep {train['departure']} | Arr {train['arrival']} | Seats {train['seats_left']} | {train['fare']}"
                    )

                prompt = (
                    f"🚆 Available trains for {origin} ➜ {dest} on {date}:\n"
                    + "\n".join(options_lines)
                    + "\n\nReply with the numbers of the services to track, separated by commas (e.g. 1,3,5)."
                )
                requests.get(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    params={"chat_id": chat_id, "text": prompt},
                )

                while not stop_event.is_set():
                    if user_selection_events[user_id].wait(timeout=1):
                        break

                if stop_event.is_set():
                    break

                selected = user_selected_services.get(user_id, [])
                if not selected:
                    selected = [train['train_service'] for train in train_data]
                    user_selected_services[user_id] = selected

                message = (
                    '🔎 Tracking only: ' + ', '.join(selected) + '\n'
                    + f'Monitoring seat changes for {origin} ➜ {dest} on {date}.'
                )
                requests.get(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    params={"chat_id": chat_id, "text": message},
                )

                analytics_message = '\n'.join(['📊 Snapshot analytics:'] + build_analytics_summary(train_data))
                requests.get(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    params={"chat_id": chat_id, "text": analytics_message},
                    timeout=10,
                )

            compare_data(train_data, previous_data, user_selected_services.get(user_id, []), token, chat_id)
            previous_data = train_data

            if stop_event.is_set():
                print('Stop requested before refresh')
                break

            for _ in range(20):
                if stop_event.is_set():
                    print('Stop requested during wait')
                    break
                sleep(0.5)

            if stop_event.is_set():
                break

            sleep(10)
            driver.refresh()

        print('Scraping loop ended')
        return {'status': 'completed', 'data': previous_data} if previous_data else {'status': 'stopped'}

    except Exception as error:
        print(f'Selenium error: {error}')
    finally:
        if db_connection is not None:
            db_connection.close()
        if driver is not None:
            driver.quit()
