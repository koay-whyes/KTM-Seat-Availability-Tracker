"""
Test script to verify KTMB login and seat selection scraping
Run this locally first before deploying to Heroku
"""

import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

def test_ktmb_login():
    """Test login to KTMB website"""

    # Get credentials from environment variables
    username = os.environ.get('KTMB_USERNAME')
    password = os.environ.get('KTMB_PASSWORD')

    if not username or not password:
        print("❌ ERROR: KTMB_USERNAME and KTMB_PASSWORD must be set as environment variables")
        print("\nTo set them:")
        print("  export KTMB_USERNAME='your_email@example.com'")
        print("  export KTMB_PASSWORD='your_password'")
        print("\nOr create a .env file with:")
        print("  KTMB_USERNAME=your_email@example.com")
        print("  KTMB_PASSWORD=your_password")
        return False

    print("=== KTMB Login Test ===\n")
    print(f"Username: {username[:3]}***{username[-10:]}")  # Partially mask for security
    print(f"Password: {'*' * len(password)}\n")

    # Setup Chrome options
    options = Options()
    # options.add_argument('--headless=new')  # Comment out to see browser for debugging
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')

    driver = None

    try:
        # Initialize Chrome driver
        print("🔄 Initializing Chrome...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)

        # Navigate to KTMB website
        print("🔄 Navigating to KTMB website...")
        driver.get('https://online.ktmb.com.my')
        time.sleep(2)

        # Look for login button/link
        print("🔄 Looking for login button...")
        try:
            # Try different selectors for login button
            login_selectors = [
                (By.LINK_TEXT, "LOGIN"),
                (By.PARTIAL_LINK_TEXT, "Login"),
                (By.PARTIAL_LINK_TEXT, "Sign In"),
                (By.XPATH, "//a[contains(text(), 'LOGIN')]"),
                (By.XPATH, "//a[contains(@href, 'login')]"),
                (By.CLASS_NAME, "login-link"),
            ]

            login_button = None
            for selector_type, selector_value in login_selectors:
                try:
                    login_button = driver.find_element(selector_type, selector_value)
                    print(f"✅ Found login button using {selector_type}: {selector_value}")
                    break
                except:
                    continue

            if not login_button:
                print("❌ Could not find login button. Taking screenshot...")
                driver.save_screenshot('ktmb_homepage.png')
                print("Screenshot saved as 'ktmb_homepage.png'")
                print("\nPage source snippet:")
                print(driver.page_source[:500])
                return False

            login_button.click()
            print("✅ Clicked login button")
            time.sleep(2)

        except Exception as e:
            print(f"❌ Error finding/clicking login button: {e}")
            driver.save_screenshot('ktmb_login_error.png')
            return False

        # Enter credentials
        print("🔄 Entering credentials...")
        try:
            # Wait for login form
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            password_field = driver.find_element(By.ID, "password")

            email_field.clear()
            email_field.send_keys(username)
            time.sleep(0.5)

            password_field.clear()
            password_field.send_keys(password)
            time.sleep(0.5)

            print("✅ Credentials entered")

            # Click login submit button
            submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
            submit_button.click()
            print("✅ Login form submitted")
            time.sleep(3)

        except Exception as e:
            print(f"❌ Error entering credentials: {e}")
            driver.save_screenshot('ktmb_credentials_error.png')
            return False

        # Check if login was successful
        print("🔄 Verifying login...")
        try:
            # Check if we're still on login page or redirected
            current_url = driver.current_url
            page_source = driver.page_source.lower()

            # Look for indicators of successful login
            if 'logout' in page_source or 'sign out' in page_source:
                print("✅ Login successful! (Found logout button)")
            elif current_url != 'https://online.ktmb.com.my/login':
                print(f"✅ Login successful! (Redirected to: {current_url})")
            else:
                print("⚠️  Login status unclear. Checking for error messages...")
                if 'invalid' in page_source or 'incorrect' in page_source or 'error' in page_source:
                    print("❌ Login failed - Invalid credentials or error")
                    driver.save_screenshot('ktmb_login_failed.png')
                    return False
                else:
                    print("✅ Assuming login successful")

        except Exception as e:
            print(f"⚠️  Error verifying login: {e}")

        # Test seat selection access
        print("\n🔄 Testing seat selection access...")
        return test_seat_selection(driver)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if driver:
            driver.save_screenshot('ktmb_error.png')
        return False

    finally:
        if driver:
            print("\n🔄 Closing browser...")
            time.sleep(2)  # Give time to see results
            driver.quit()

def test_seat_selection(driver):
    """Test accessing seat selection after login"""

    try:
        # Navigate to trip search
        print("🔄 Navigating to trip search...")
        driver.get('https://online.ktmb.com.my/Trip')
        time.sleep(2)

        # Fill in a test search (KL Sentral to Alor Setar)
        print("🔄 Filling search form...")

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

        # Set a future date (you might need to adjust this)
        date_field = driver.find_element(By.ID, "OnwardDate")
        driver.execute_script("arguments[0].value = '2 Jan 2026';", date_field)
        time.sleep(1)

        # Submit search
        search_button = driver.find_element(By.ID, "btnSubmit")
        search_button.click()
        print("✅ Search submitted")
        time.sleep(5)

        # Look for "Pick Seats" button
        print("🔄 Looking for 'Pick Seats' button...")
        try:
            # Try to find Pick Seats button
            pick_seats_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Pick Seats')]")

            if pick_seats_buttons:
                print(f"✅ Found {len(pick_seats_buttons)} 'Pick Seats' button(s)!")

                # Click the first one
                print("🔄 Clicking 'Pick Seats' button...")
                pick_seats_buttons[0].click()
                time.sleep(3)

                # Check if seat selection modal appeared
                print("🔄 Checking for seat selection modal...")

                # Look for seat elements
                seat_elements = driver.find_elements(By.CLASS_NAME, "seat")
                if seat_elements:
                    print(f"✅ Seat selection modal opened! Found {len(seat_elements)} seat elements")

                    # Parse seat information
                    print("\n🔄 Parsing seat information...")
                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    # Count different seat statuses
                    seats = soup.find_all(class_='seat')
                    seat_status = {
                        'available': 0,
                        'reserved': 0,
                        'blocked': 0,
                        'sold': 0
                    }

                    for seat in seats[:20]:  # Sample first 20 seats
                        classes = ' '.join(seat.get('class', []))
                        if 'reserved' in classes:
                            seat_status['reserved'] += 1
                        elif 'blocked' in classes:
                            seat_status['blocked'] += 1
                        elif 'sold' in classes:
                            seat_status['sold'] += 1
                        else:
                            seat_status['available'] += 1

                    print(f"\nSeat Status (sample of 20 seats):")
                    print(f"  Available: {seat_status['available']}")
                    print(f"  Reserved: {seat_status['reserved']}")
                    print(f"  Blocked: {seat_status['blocked']}")
                    print(f"  Sold: {seat_status['sold']}")

                    driver.save_screenshot('ktmb_seat_selection.png')
                    print("\n✅ Screenshot saved as 'ktmb_seat_selection.png'")

                    return True
                else:
                    print("⚠️  Seat selection modal may not have opened properly")
                    driver.save_screenshot('ktmb_no_seats.png')
                    return False

            else:
                print("❌ No 'Pick Seats' button found")
                print("This might mean:")
                print("  1. Login was not successful")
                print("  2. No trains available for this route/date")
                print("  3. Button has different text/class")

                driver.save_screenshot('ktmb_no_pick_seats.png')
                print("Screenshot saved as 'ktmb_no_pick_seats.png'")
                return False

        except Exception as e:
            print(f"❌ Error accessing seat selection: {e}")
            driver.save_screenshot('ktmb_seat_error.png')
            return False

    except Exception as e:
        print(f"❌ Error in seat selection test: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    success = test_ktmb_login()
    print("="*60)

    if success:
        print("\n✅ ALL TESTS PASSED!")
        print("You can now proceed with implementing this in the main bot.")
    else:
        print("\n❌ TESTS FAILED")
        print("Please check the error messages and screenshots above.")
        print("Fix any issues before proceeding.")
