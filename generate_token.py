#!/usr/bin/env python3
"""
Upstox Token Generator

This script generates Upstox access tokens for multiple API keys and stores them in the database.
It's designed to be run as a daily scheduled task at 5 AM.

Usage:
  - Run manually: python generate_token.py
  - Schedule with cron: 0 5 * * * cd /path/to/option-chain-python && python generate_token.py

Options:
  --visible: Run in visible browser mode (for debugging only)
  --manual: Use manual authentication flow instead of automated
  --add-account: Add a new Upstox account to the database
  --browser: Specify preferred browser (chrome or firefox)
  --install-deps: Install browser dependencies for Railway deployment
"""

import argparse
import os
import getpass
import logging
import sys
import subprocess
from datetime import datetime
from upstox_auth import automated_auth_flow, manual_auth_flow, fully_automated_auth_flow, detect_browsers
from dotenv import load_dotenv
from config import Config
from database import DatabaseService

# Configure logging
logging.basicConfig(
    filename='token_generation.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize database service
db_service = DatabaseService()

def get_account_details():
    """Prompt the user for account details"""
    print("\n=== Add Upstox Account ===")
    api_key = input("API Key: ")
    api_secret = input("API Secret: ")
    totp_secret = input("TOTP Secret: ")
    redirect_uri = input("Redirect URI [http://localhost:5000/callback]: ") or "http://localhost:5000/callback"
    username = input("Upstox Username: ")
    password = getpass.getpass("Upstox Password: ")
    
    return {
        'api_key': api_key,
        'api_secret': api_secret,
        'totp_secret': totp_secret,
        'redirect_uri': redirect_uri,
        'username': username,
        'password': password,
        'is_active': True
    }

def add_account():
    """Add a new account to the database"""
    account_data = get_account_details()

    if db_service.save_upstox_account(account_data):
        print("Account saved successfully!")
        return True
    else:
        print("Failed to save account.")
        return False

def install_browser_dependencies():
    """Install browser dependencies for Railway deployment"""
    print("Installing browser dependencies for Railway deployment...")
    
    try:
        # Update package lists
        print("Updating package lists...")
        subprocess.run(["apt-get", "update"], check=True)
        
        # Try installing Firefox (regular version)
        print("Attempting to install Firefox...")
        try:
            subprocess.run([
                "apt-get", "install", "-y", "firefox", "wget", "bzip2", 
                "libxtst6", "libgtk-3-0", "libx11-xcb1", "libdbus-glib-1-2", 
                "libxt6", "libpci3"
            ], check=True)
            print("Firefox installed successfully!")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install Firefox: {str(e)}")
            
            # Try installing Chromium as a fallback
            print("Attempting to install Chromium as fallback...")
            try:
                subprocess.run([
                    "apt-get", "install", "-y", "chromium-browser", "wget", "bzip2", 
                    "libxtst6", "libgtk-3-0", "libx11-xcb1", "libdbus-glib-1-2", 
                    "libxt6", "libpci3"
                ], check=True)
                print("Chromium installed successfully!")
            except subprocess.CalledProcessError as e2:
                print(f"Failed to install Chromium: {str(e2)}")
                
                # Try with add-apt-repository to get Firefox
                try:
                    print("Attempting to add Mozilla PPA...")
                    subprocess.run(["apt-get", "install", "-y", "software-properties-common"], check=True)
                    subprocess.run(["add-apt-repository", "ppa:mozillateam/ppa", "-y"], check=True)
                    subprocess.run(["apt-get", "update"], check=True)
                    subprocess.run(["apt-get", "install", "-y", "firefox"], check=True)
                    print("Firefox installed from Mozilla PPA!")
                except subprocess.CalledProcessError as e3:
                    print(f"Failed to install Firefox from Mozilla PPA: {str(e3)}")
                    print("Continuing without browser installation. Will try to use existing browsers or fall back to manual mode.")
        
        # Install WebDrivers regardless of which browser was installed
        print("Installing WebDriver managers...")
        try:
            # Install Firefox GeckoDriver
            print("Installing GeckoDriver...")
            subprocess.run([
                "wget", "-q", "https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux64.tar.gz"
            ], check=True)
            subprocess.run(["tar", "-xzf", "geckodriver-v0.33.0-linux64.tar.gz"], check=True)
            subprocess.run(["chmod", "+x", "geckodriver"], check=True)
            subprocess.run(["mv", "geckodriver", "/usr/local/bin/"], check=True)
            print("GeckoDriver installed!")
        except Exception as e:
            print(f"Error installing GeckoDriver: {str(e)}")
        
        try:
            # Install ChromeDriver
            print("Installing ChromeDriver...")
            subprocess.run([
                "wget", "-q", "https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip"
            ], check=True)
            subprocess.run(["apt-get", "install", "-y", "unzip"], check=True)
            subprocess.run(["unzip", "chromedriver_linux64.zip"], check=True)
            subprocess.run(["chmod", "+x", "chromedriver"], check=True)
            subprocess.run(["mv", "chromedriver", "/usr/local/bin/"], check=True)
            print("ChromeDriver installed!")
        except Exception as e:
            print(f"Error installing ChromeDriver: {str(e)}")
        
        # Check which browsers are now available
        available_browsers = detect_browsers()
        if available_browsers:
            print(f"Successfully installed browser(s): {', '.join(available_browsers)}")
            return True
        else:
            print("Warning: No browsers were detected after installation")
            print("Will fall back to manual authentication mode")
            return False
            
    except Exception as e:
        print(f"Error during browser dependency installation: {str(e)}")
        print("Will fall back to manual authentication mode")
        return False

def generate_token_for_account(account, headless=True, manual=False, browser=None):
    """Generate a token for a specific account"""
    api_key = account.get('api_key')
    api_secret = account.get('api_secret')
    totp_secret = account.get('totp_secret')
    redirect_uri = account.get('redirect_uri')
    username = account.get('username')
    password = account.get('password')
    
    if not all([api_key, api_secret, totp_secret, redirect_uri]):
        logging.error(f"Missing required credentials for account {api_key}")
        return False
    
    logging.info(f"Generating token for account {api_key}")
    
    # Check if using manual flow
    if manual:
        logging.info(f"Using manual flow for account {api_key}")
        access_token = manual_auth_flow(api_key, api_secret, totp_secret, redirect_uri)
    else:
        # Check if we have username/password for fully automated flow
        if username and password:
            logging.info(f"Using fully automated flow for account {api_key}")
            access_token = fully_automated_auth_flow(
                api_key, api_secret, totp_secret, redirect_uri,
                headless=headless, username=username, password=password
            )
        else:
            logging.info(f"Using semi-automated flow for account {api_key}")
            access_token = automated_auth_flow(api_key, api_secret, totp_secret, redirect_uri)
    
    # Check if token generation was successful
    if access_token:
        logging.info(f"Token generation successful for account {api_key}")
        
        # Create token data structure with required fields
        token_data = {
            'access_token': access_token,
            'created_at': datetime.now().timestamp()
        }

        # Update token directly in database
        if db_service.update_upstox_token(api_key, token_data):
            logging.info(f"Token updated in database for account {api_key}")
            return True
        else:
            logging.error(f"Failed to update token in database for account {api_key}")
    else:
        logging.error(f"Token generation failed for account {api_key}")
    
    return False

def main():
    parser = argparse.ArgumentParser(description='Generate Upstox access tokens for multiple accounts')
    parser.add_argument('--visible', action='store_true', help='Run browser in visible mode (for debugging)')
    parser.add_argument('--manual', action='store_true', help='Use manual flow instead of automated')
    parser.add_argument('--add-account', action='store_true', help='Add a new Upstox account to the database')
    parser.add_argument('--browser', choices=['chrome', 'firefox'], help='Specify preferred browser to use')
    parser.add_argument('--install-deps', action='store_true', help='Install browser dependencies for Railway deployment')
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Install browser dependencies if requested (for Railway)
    if args.install_deps:
        if install_browser_dependencies():
            logging.info("Browser dependencies installed successfully")
        else:
            logging.warning("Failed to install all browser dependencies, continuing anyway")
    
    # Add account if requested
    if args.add_account:
        if add_account():
            logging.info("New account added successfully")
        else:
            logging.error("Failed to add new account")
            sys.exit(1)
        return
    
    # Check for Railway environment
    is_railway = os.environ.get('RAILWAY_ENVIRONMENT') == 'production'
    if is_railway:
        logging.info("Detected Railway deployment environment")
        print("Detected Railway deployment environment")
        
        # Force headless mode in Railway
        headless = True
        
        # Detect available browsers in Railway environment
        available_browsers = detect_browsers()
        if not available_browsers and not args.manual:
            logging.warning("No browsers detected in Railway environment, falling back to manual mode")
            print("No browsers detected in Railway environment, falling back to manual mode")
            args.manual = True
    else:
        headless = not args.visible
    
    # Get accounts from database
    accounts = db_service.get_upstox_accounts()
    
    if not accounts:
        logging.error("No accounts found in database")
        print("No accounts found. Use --add-account to add a new account.")
        sys.exit(1)
    
    # Generate tokens for each account
    success_count = 0
    for account in accounts:
        if generate_token_for_account(account, headless=headless, manual=args.manual, browser=args.browser):
            success_count += 1
    
    # Log summary
    logging.info(f"Token generation complete. Generated {success_count}/{len(accounts)} tokens successfully.")
    print(f"Token generation complete. Generated {success_count}/{len(accounts)} tokens successfully.")
    
    # Exit with appropriate code
    sys.exit(0 if success_count == len(accounts) else 1)

if __name__ == "__main__":
    main()
