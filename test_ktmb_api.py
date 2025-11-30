"""
Test script to explore KTMB website API without authentication
This will help us understand if seat data is accessible without login
"""

import requests
from bs4 import BeautifulSoup
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

def test_direct_api_calls():
    """Test if there are any direct API endpoints we can access"""
    print("=== Testing Direct API Calls ===")

    # Common API endpoints to try
    base_url = "https://online.ktmb.com.my"
    endpoints = [
        "/api/trips",
        "/api/seats",
        "/api/booking",
        "/Trip/GetSeats",
        "/Trip/GetAvailability",
        "/api/availability",
    ]

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    for endpoint in endpoints:
        try:
            url = base_url + endpoint
            response = session.get(url)
            print(f"\n{endpoint}: Status {response.status_code}")
            if response.status_code == 200:
                print(f"  Content preview: {response.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")

def test_network_requests():
    """Use Selenium to capture network requests when accessing seat selection"""
    print("\n=== Testing Network Requests with Selenium ===")

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    # Enable performance logging to capture network requests
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Go to the trip search page
        driver.get('https://online.ktmb.com.my')
        time.sleep(3)

        print("\nSearching for a train...")

        # Fill in search form (example: KL Sentral to Alor Setar)
        try:
            origin_select = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "select2-FromStationId-container"))
            )
            origin_select.click()
            time.sleep(1)

            origin_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@class='station-name' and text()='KL SENTRAL']"))
            )
            origin_option.click()
            time.sleep(1)

            dest_select = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "select2-ToStationId-container"))
            )
            dest_select.click()
            time.sleep(1)

            dest_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@class='station-name' and text()='ALOR SETAR']"))
            )
            dest_option.click()
            time.sleep(1)

            # Click search
            search_button = driver.find_element(By.ID, "btnSubmit")
            search_button.click()
            time.sleep(5)

            print("\nTrain results loaded. Checking for seat selection buttons...")

            # Try to find "Select Seat" or similar buttons
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # Look for any links or buttons related to seat selection
            seat_buttons = soup.find_all(['a', 'button'], string=lambda text: text and 'seat' in text.lower())
            print(f"Found {len(seat_buttons)} elements with 'seat' in text")

            for i, btn in enumerate(seat_buttons[:3]):  # Show first 3
                print(f"  {i+1}. {btn.get('class')}: {btn.text.strip()[:50]}")
                if btn.get('href'):
                    print(f"     href: {btn.get('href')}")
                if btn.get('onclick'):
                    print(f"     onclick: {btn.get('onclick')[:100]}")

            # Check network logs for API calls
            print("\nAnalyzing network requests...")
            logs = driver.get_log('performance')

            api_calls = []
            for entry in logs:
                log = json.loads(entry['message'])['message']
                if log['method'] == 'Network.requestWillBeSent':
                    url = log['params']['request']['url']
                    if 'api' in url.lower() or 'seat' in url.lower() or 'trip' in url.lower():
                        api_calls.append(url)

            print(f"\nFound {len(api_calls)} relevant API calls:")
            for call in set(api_calls):  # Remove duplicates
                print(f"  - {call}")

        except Exception as e:
            print(f"Error during automation: {e}")
            print("Taking screenshot of current page...")
            driver.save_screenshot('/tmp/ktmb_test.png')

        driver.quit()

    except Exception as e:
        print(f"Error initializing driver: {e}")

def test_seat_selection_access():
    """Test if we can access seat selection page directly"""
    print("\n=== Testing Direct Seat Selection Access ===")

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # Try accessing seat selection page directly
    urls_to_test = [
        'https://online.ktmb.com.my/Trip/SelectSeats',
        'https://online.ktmb.com.my/Trip/Seats',
        'https://online.ktmb.com.my/Booking/Seats',
    ]

    for url in urls_to_test:
        try:
            response = session.get(url)
            print(f"\n{url}")
            print(f"  Status: {response.status_code}")
            print(f"  Redirected to: {response.url}")

            # Check if we were redirected to login
            if 'login' in response.url.lower() or 'signin' in response.url.lower():
                print("  ❌ Redirected to login - authentication required")
            elif response.status_code == 200:
                print("  ✅ Page accessible!")

        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    print("KTMB API Exploration - Testing Unauthenticated Access\n")
    print("="*60)

    # Test 1: Direct API calls
    test_direct_api_calls()

    # Test 2: Direct page access
    test_seat_selection_access()

    # Test 3: Network request analysis (requires Selenium)
    print("\n\nDo you want to run Selenium tests? (y/n): ", end="")
    response = input().strip().lower()
    if response == 'y':
        test_network_requests()

    print("\n" + "="*60)
    print("Analysis complete!")
