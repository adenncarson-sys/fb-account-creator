#!/usr/bin/env python3
"""
Browser automation module – wraps undetected-chromedriver with Facebook signup + verification.
Auto-detects Termux (Android) environment and adjusts paths accordingly.
"""

import os
import sys
import time
import random
import re
import platform
from typing import Optional, Tuple, Dict
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementClickInterceptedException
)

from logger_utils import log
from account_gen import AccountProfile
from captcha_solver import CaptchaSolver
from email_handler import get_email_handler


# ═════════════════════════════════════════════════════════════════════════════
#  TERMUX DETECTION & PATHS
# ═════════════════════════════════════════════════════════════════════════════

TERMUX_PREFIX = "/data/data/com.termux/files/usr"
IS_TERMUX = (
    platform.system() == "Linux"
    and os.path.exists("/data/data/com.termux")
    and os.path.exists(TERMUX_PREFIX)
)

TERMUX_CHROMIUM_BIN = f"{TERMUX_PREFIX}/bin/chromium-browser"
TERMUX_CHROMEDRIVER = f"{TERMUX_PREFIX}/lib/chromium/chromedriver"


def detect_environment() -> dict:
    """
    Detect the current environment (Termux, Linux desktop, etc.)
    and return the appropriate browser paths and flags.
    """
    env = {
        "is_termux": IS_TERMUX,
        "browser_binary": None,
        "chromedriver_path": None,
        "extra_args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
        ],
        "use_virtual_display": False,
    }

    if IS_TERMUX:
        log.info("Detected Termux (Android) environment")
        env["browser_binary"] = TERMUX_CHROMIUM_BIN
        env["chromedriver_path"] = TERMUX_CHROMEDRIVER
        env["extra_args"].extend([
            "--disable-setuid-sandbox",
            "--disable-extensions",
            "--disable-sync",
            "--disable-translate",
            "--hide-scrollbars",
            "--mute-audio",
            "--ignore-certificate-errors",
        ])
        if not os.path.exists(TERMUX_CHROMIUM_BIN):
            log.warning(f"Chromium not found at {TERMUX_CHROMIUM_BIN}")
            log.warning("Run: pkg install tur-repo && pkg install chromium")
    else:
        log.debug("Detected standard Linux environment")

    return env


class FacebookBrowser:
    """Manage undetected Chrome browser and automate Facebook registration + verification."""

    SIGNUP_URL = "https://www.facebook.com/reg/"
    FB_HOME = "https://www.facebook.com/"
    LOGIN_URL = "https://www.facebook.com/login/"

    def __init__(self, headless: bool = False, proxy: str = "",
                 page_timeout: int = 30, implicit_wait: int = 10,
                 captcha_solver: Optional[CaptchaSolver] = None,
                 email_backend: str = "mail.tm"):
        self.headless = headless
        self.proxy = proxy
        self.page_timeout = page_timeout
        self.implicit_wait = implicit_wait
        self.captcha_solver = captcha_solver or CaptchaSolver()
        self.email_backend = email_backend
        self.driver = None
        self.email_handler = None
        self.env = detect_environment()
        self._virtual_display = None

    def _create_driver(self):
        """Initialize undetected ChromeDriver with environment-specific config."""
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()

        # Core privacy / anti-detection flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"--window-size={1366},{768}")

        # Environment-specific flags
        for arg in self.env["extra_args"]:
            options.add_argument(arg)

        # Headless
        if self.headless:
            if IS_TERMUX:
                options.add_argument("--headless")       # Termux: OLD headless flag
            else:
                options.add_argument("--headless=new")    # Desktop: new headless

        # Proxy
        if self.proxy:
            options.add_argument(f"--proxy-server={self.proxy}")

        # User agent (mobile for less scrutiny)
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Linux; Android 10; K) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Mobile Safari/537.36"
        )

        # Binary location (Termux needs explicit path)
        if self.env["browser_binary"]:
            options.binary_location = self.env["browser_binary"]

        # Virtual display for Termux headed mode
        if IS_TERMUX and not self.headless:
            if "DISPLAY" not in os.environ or not os.environ["DISPLAY"]:
                try:
                    from pyvirtualdisplay import Display
                    self._virtual_display = Display(visible=False, size=(1366, 768))
                    self._virtual_display.start()
                    log.info("Virtual display started (Xvfb)")
                except ImportError:
                    log.warning(
                        "pyvirtualdisplay not installed. Install: pip install pyvirtualdisplay\n"
                        "Or use --headless mode, or start a VNC server and set DISPLAY=:1"
                    )

        # Initialize the driver
        driver_kwargs = {"options": options}

        if IS_TERMUX and os.path.exists(self.env["chromedriver_path"]):
            driver_kwargs["driver_executable_path"] = self.env["chromedriver_path"]
            log.debug(f"Using chromedriver at: {self.env['chromedriver_path']}")

        self.driver = uc.Chrome(**driver_kwargs)
        self.driver.implicitly_wait(self.implicit_wait)
        self.driver.set_page_load_timeout(self.page_timeout)
        log.info("Browser initialized")

    def _random_delay(self, low: float = 0.5, high: float = 2.0):
        time.sleep(random.uniform(low, high))

    def _find_and_send(self, by, selector: str, text: str, delay: bool = True):
        el = self.driver.find_element(by, selector)
        el.clear()
        el.send_keys(text)
        if delay:
            self._random_delay(0.2, 0.8)

    def _select_dropdown(self, by, selector: str, value: str):
        el = self.driver.find_element(by, selector)
        select = Select(el)
        try:
            select.select_by_value(value)
        except Exception:
            try:
                select.select_by_visible_text(value)
            except Exception:
                select.select_by_index(1)

    # ═══════════════════════════════════════════════════════════════════════
    #  VERIFICATION – log in and check account status
    # ═══════════════════════════════════════════════════════════════════════

    def verify_account(self, email: str, password: str) -> Dict[str, str]:
        """
        Attempt to log in to Facebook and check account status.
        Returns {"ok": "TRUE"/"FALSE", "reason": "..."}
        """
        if not self.driver:
            self._create_driver()

        log.info(f"Verifying account: {email}")

        try:
            self.driver.get(self.FB_HOME)
            self._random_delay(2, 4)
        except Exception as e:
            return {"ok": "FALSE", "reason": f"Navigation failed: {e}"}

        # Already on a checkpoint page?
        current_url = self.driver.current_url.lower()
        if "checkpoint" in current_url:
            return self._check_restriction_page()

        if self._is_homepage_reached():
            return {"ok": "TRUE", "reason": "Already logged in – homepage active"}

        # Fill login form
        try:
            email_selectors = [
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[type='text'][name='email']"),
                (By.XPATH, "//input[@placeholder='Email address or phone number']"),
                (By.XPATH, "//input[@placeholder='Email or phone']"),
            ]
            email_field = None
            for by, sel in email_selectors:
                try:
                    email_field = WebDriverWait(self.driver, 4).until(
                        EC.presence_of_element_located((by, sel))
                    )
                    break
                except TimeoutException:
                    continue

            if email_field is None:
                if self._is_homepage_reached():
                    return {"ok": "TRUE", "reason": "Already logged in – homepage reached"}
                restriction = self._detect_restriction()
                if restriction:
                    return {"ok": "FALSE", "reason": restriction}
                return {"ok": "FALSE", "reason": "Could not locate login form"}

            email_field.clear()
            email_field.send_keys(email)
            self._random_delay(0.5, 1.5)

            pass_selectors = [
                (By.ID, "pass"),
                (By.NAME, "pass"),
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.XPATH, "//input[@placeholder='Password']"),
            ]
            pass_field = None
            for by, sel in pass_selectors:
                try:
                    pass_field = WebDriverWait(self.driver, 4).until(
                        EC.presence_of_element_located((by, sel))
                    )
                    break
                except TimeoutException:
                    continue

            if pass_field is None:
                return {"ok": "FALSE", "reason": "Could not locate password field"}

            pass_field.clear()
            pass_field.send_keys(password)
            self._random_delay(0.5, 1.5)

            login_selectors = [
                (By.NAME, "login"),
                (By.ID, "loginbutton"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(),'Log in')]"),
            ]
            login_btn = None
            for by, sel in login_selectors:
                try:
                    login_btn = WebDriverWait(self.driver, 4).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    break
                except TimeoutException:
                    continue

            if login_btn:
                login_btn.click()
                self._random_delay(3, 6)
            else:
                pass_field.send_keys("\ue007")  # Enter key
                self._random_delay(3, 6)

        except Exception as e:
            return {"ok": "FALSE", "reason": f"Login form error: {e}"}

        return self._evaluate_post_login_state()

    def _evaluate_post_login_state(self) -> Dict[str, str]:
        """Check the page after login and determine account status."""
        self._random_delay(2, 4)
        current_url = self.driver.current_url.lower()

        restriction = self._detect_restriction()
        if restriction:
            return {"ok": "FALSE", "reason": restriction}

        if "/checkpoint/" in current_url:
            page_text = self._get_body_text()
            if "suspended" in page_text:
                return {"ok": "FALSE", "reason": "Account suspended (checkpoint page)"}
            if "disabled" in page_text:
                return {"ok": "FALSE", "reason": "Account disabled (checkpoint page)"}
            if "review" in page_text:
                return {"ok": "FALSE", "reason": "Account under review (checkpoint page)"}
            if "confirm your identity" in page_text or "verify your identity" in page_text:
                return {"ok": "FALSE", "reason": "Identity verification required (checkpoint)"}
            return {"ok": "FALSE", "reason": "Account checkpoint triggered"}

        if "login" in current_url and "checkpoint" not in current_url:
            try:
                error_el = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "div[role='alert'], ._50f4, ._5yd0, #error_box, "
                    "div[data-testid='login_error'], .uiContextualMessage"
                )
                error_text = error_el.text.strip()
                if error_text:
                    return {"ok": "FALSE", "reason": f"Login error: {error_text}"}
            except NoSuchElementException:
                pass
            return {"ok": "FALSE", "reason": "Login page returned – credentials may be invalid"}

        # Check for 2FA / login approval
        body_text = self._get_body_text()
        for kw in [
            "approve from your", "enter the code", "two-factor",
            "authentication required", "login approval", "enter login code",
            "we sent a code", "check your email for a code",
        ]:
            if kw in body_text:
                return {"ok": "FALSE", "reason": f"Login approval required ({kw})"}

        if self._is_homepage_reached():
            return {"ok": "TRUE", "reason": "Account active – homepage reached"}

        return {"ok": "FALSE", "reason": f"Unknown account state (URL: {current_url[:120]})"}

    def _get_body_text(self) -> str:
        try:
            return self.driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            return ""

    def _detect_restriction(self) -> Optional[str]:
        """Scan the page for known restriction/suspension/disablement messages."""
        body_text = self._get_body_text()

        patterns = [
            ("your account has been permanently disabled", "Account permanently disabled"),
            ("we've disabled your account", "Account disabled"),
            ("we've suspended your account", "Account suspended"),
            ("your account has been suspended", "Account suspended"),
            ("your account is under review", "Account under review"),
            ("we need more information to confirm your identity", "Identity verification required"),
            ("you need to confirm your identity", "Identity confirmation required"),
            ("confirm your identity", "Identity verification checkpoint"),
            ("we need you to verify your identity", "Identity verification required"),
            ("your account is temporarily locked", "Account temporarily locked"),
            ("you can't use this feature at the moment", "Feature restricted"),
            ("you have been locked out", "Account locked out"),
            ("this action is temporarily restricted", "Temporary restriction"),
            ("we'll take another look at your account", "Under review"),
        ]

        for pattern, reason in patterns:
            if pattern in body_text:
                return reason

        try:
            current_url = self.driver.current_url.lower()
            if "/checkpoint/" in current_url:
                return "General checkpoint page"
            if "/identity/" in current_url or "/confirm/" in current_url:
                return "Identity check required"
        except Exception:
            pass

        return None

    def _check_restriction_page(self) -> Dict[str, str]:
        restriction = self._detect_restriction()
        if restriction:
            return {"ok": "FALSE", "reason": restriction}
        return {"ok": "FALSE", "reason": "Stuck on checkpoint page (unknown reason)"}

    def _is_homepage_reached(self) -> bool:
        """Check if we've reached the Facebook news feed / homepage."""
        indicators = [
            "//*[contains(text(),\"What's on your mind\")]",
            "//*[contains(text(),\"what's on your mind\")]",
            "//*[@aria-label=\"What's on your mind?\"]",
            "//*[@aria-label='What’s on your mind?']",
            "//*[@role='feed']",
            "//*[@data-pagelet='FeedUnit']",
            "//*[@data-pagelet='MainFeed']",
            "//a[@aria-label='Home']",
            "//a[@aria-label='Facebook']",
        ]
        for xpath in indicators:
            try:
                if self.driver.find_elements(By.XPATH, xpath):
                    return True
            except Exception:
                continue
        try:
            url = self.driver.current_url.lower()
            if "facebook.com/" in url and not any(
                kw in url for kw in ["login", "reg/", "checkpoint", "confirm",
                                     "identity", "signup", "recover", "help"]
            ):
                return True
        except Exception:
            pass
        return False

    # ═══════════════════════════════════════════════════════════════════════
    #  SIGNUP
    # ═══════════════════════════════════════════════════════════════════════

    def signup(self, profile: AccountProfile) -> Tuple[bool, str]:
        """
        Execute the full Facebook signup flow for one profile.
        Returns (success: bool, message: str).
        """
        if not self.driver:
            self._create_driver()

        # ── 1. Create temp email if needed ─────────────────────────────────
        email_to_use = profile.email
        if not email_to_use:
            try:
                self.email_handler = get_email_handler(self.email_backend)
                email_to_use = self.email_handler.create_inbox()
                profile.email = email_to_use
            except Exception as e:
                log.error(f"Failed to create temp email: {e}")
                return False, f"Temp email creation failed: {e}"
        else:
            self.email_handler = None

        log.info(f"Registering: {profile.first_name} {profile.last_name} "
                 f"<{email_to_use}>")

        # ── 2. Navigate ────────────────────────────────────────────────────
        try:
            self.driver.get(self.FB_HOME)
            self._random_delay(1, 3)
        except Exception as e:
            return False, f"Navigation failed: {e}"

        # ── 3. Click "Create New Account" ──────────────────────────────────
        try:
            selectors = [
                (By.PARTIAL_LINK_TEXT, "Create new account"),
                (By.XPATH, "//a[contains(text(),'Create new account')]"),
                (By.XPATH, "//a[contains(@data-testid,'open-registration-form-button')]"),
                (By.XPATH, "//*[text()='Create new account']"),
            ]
            btn = None
            for by, sel in selectors:
                try:
                    btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    break
                except TimeoutException:
                    continue
            if btn is None:
                self.driver.get(self.SIGNUP_URL)
                self._random_delay(1, 2)
            else:
                btn.click()
                self._random_delay(1, 2)
        except Exception as e:
            return False, f"Could not open registration form: {e}"

        # ── 4. Fill form ──────────────────────────────────────────────────
        try:
            self._find_and_send(By.NAME, "firstname", profile.first_name)
            self._find_and_send(By.NAME, "lastname", profile.last_name)
            self._find_and_send(By.NAME, "reg_email__", email_to_use)

            try:
                confirm_el = self.driver.find_element(By.NAME, "reg_email_confirmation__")
                confirm_el.send_keys(email_to_use)
                self._random_delay(0.3, 0.8)
            except NoSuchElementException:
                pass

            self._find_and_send(By.NAME, "reg_passwd__", profile.password)

            self._select_dropdown(By.NAME, "birthday_day", profile.dob_day)
            self._random_delay(0.2, 0.5)
            self._select_dropdown(By.NAME, "birthday_month", profile.dob_month)
            self._random_delay(0.2, 0.5)
            self._select_dropdown(By.NAME, "birthday_year", profile.dob_year)
            self._random_delay(0.3, 0.6)

            gender_btns = self.driver.find_elements(
                By.CSS_SELECTOR, "input[name='sex']"
            )
            for btn in gender_btns:
                if btn.get_attribute("value") == profile.gender:
                    btn.click()
                    break
            self._random_delay(0.3, 0.7)

            log.info("Form filled – submitting...")
        except Exception as e:
            return False, f"Form filling error: {e}"

        # ── 5. Submit ──────────────────────────────────────────────────────
        try:
            submit_selectors = [
                (By.NAME, "websubmit"),
                (By.XPATH, "//button[contains(text(),'Sign Up')]"),
                (By.XPATH, "//button[contains(text(),'Submit')]"),
                (By.CSS_SELECTOR, "button[type='submit']"),
            ]
            submit_btn = None
            for by, sel in submit_selectors:
                try:
                    submit_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    break
                except TimeoutException:
                    continue
            if submit_btn:
                submit_btn.click()
                self._random_delay(2, 4)
            else:
                return False, "Could not find submit button"
        except ElementClickInterceptedException:
            log.warning("Submit button intercepted – possible overlay")
            self._random_delay(1, 2)
            try:
                self.driver.execute_script(
                    "document.querySelector('button[name=\"websubmit\"]').click()"
                )
            except Exception:
                return False, "Submit button click failed"
        except Exception as e:
            return False, f"Submit error: {e}"

        # ── 6. Handle CAPTCHA ──────────────────────────────────────────────
        try:
            captcha_iframes = self.driver.find_elements(
                By.CSS_SELECTOR,
                "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
                "iframe[title*='captcha'], iframe[src*='challenge']"
            )
            if captcha_iframes:
                log.info("CAPTCHA detected on the page")
                site_key = ""
                try:
                    src = captcha_iframes[0].get_attribute("src")
                    m = re.search(r"[&?]k=([a-zA-Z0-9_-]+)", src)
                    if m:
                        site_key = m.group(1)
                except Exception:
                    pass
                result = self.captcha_solver.solve_fb(
                    self.driver, site_key=site_key,
                    page_url=self.driver.current_url
                )
                if result is None:
                    return False, "CAPTCHA solving failed"
        except Exception:
            pass

        # ── 7. Handle email confirmation ──────────────────────────────────
        self._random_delay(3, 6)
        current_url = self.driver.current_url.lower()

        if "confirm" in current_url or "checkpoint" in current_url:
            log.info("Email confirmation page detected – fetching code from inbox...")
            if self.email_handler:
                self._random_delay(2, 4)
                msg_text = self.email_handler.wait_for_message(timeout=60)
                if msg_text:
                    codes = re.findall(r"\b(\d{6})\b", msg_text)
                    for code in codes:
                        log.info(f"Found confirmation code candidate: {code}")
                        try:
                            code_input = self.driver.find_element(
                                By.CSS_SELECTOR,
                                "input[type='text'], input[type='number'], "
                                "input[name*='code']"
                            )
                            code_input.clear()
                            code_input.send_keys(code)
                            self._random_delay(0.5, 1.5)
                            next_btn = self.driver.find_element(
                                By.XPATH,
                                "//button[contains(text(),'Confirm')] | "
                                "//button[contains(text(),'Next')] | "
                                "//button[contains(text(),'Submit')]"
                            )
                            next_btn.click()
                            self._random_delay(2, 4)
                            log.info(f"Submitted confirmation code: {code}")
                            break
                        except Exception:
                            continue
                else:
                    log.warning("No confirmation email received within timeout")
        else:
            log.info("No confirmation page detected")

        # ── 8. Check post-signup state ────────────────────────────────────
        self._random_delay(2, 4)
        final_url = self.driver.current_url.lower()

        if "checkpoint" in final_url:
            return False, "Checkpoint triggered after signup"
        if "confirm" in final_url:
            return False, "Stuck on confirmation page"
        if "reg" in final_url or "signup" in final_url:
            return False, "Still on registration page – possible validation error"

        if self._is_homepage_reached():
            return True, "Account created – homepage active"

        if "facebook.com" in final_url and "reg" not in final_url:
            return True, f"Account created (URL: {final_url[:80]})"

        return True, f"Signup completed (final URL: {final_url[:80]})"

    def close(self):
        """Clean up browser, temp email, and virtual display."""
        if self.email_handler:
            try:
                self.email_handler.cleanup()
            except Exception:
                pass
        if self.driver:
            try:
                self.driver.quit()
                log.info("Browser closed")
            except Exception:
                pass
        if self._virtual_display:
            try:
                self._virtual_display.stop()
                log.info("Virtual display stopped")
            except Exception:
                pass
