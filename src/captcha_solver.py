#!/usr/bin/env python3
"""
CAPTCHA solving integration – 2captcha / Anti-Captcha stubs + manual fallback.
"""

import time
import requests
from typing import Optional
from logger_utils import log


class CaptchaSolver:
    """Unified solver wrapper."""

    def __init__(self, service: str = "manual", api_key: str = ""):
        self.service = service
        self.api_key = api_key

    def solve_fb(self, driver, site_key: str = "",
                 page_url: str = "https://www.facebook.com/reg/") -> Optional[str]:
        """
        Solve Facebook CAPTCHA.
        For 'manual' mode, prompt the user.
        """
        if self.service == "manual":
            log.info("CAPTCHA detected – please solve it manually in the browser.")
            input("  → Press Enter after solving the CAPTCHA...")
            return "manual_ok"

        if not self.api_key:
            log.warning("No CAPTCHA API key configured – falling back to manual")
            input("  → Press Enter after solving the CAPTCHA...")
            return "manual_ok"

        if self.service == "2captcha":
            return self._solve_2captcha(site_key, page_url)

        log.error(f"Unsupported captcha service: {self.service}")
        return None

    def _solve_2captcha(self, site_key: str, page_url: str) -> Optional[str]:
        log.info("Submitting CAPTCHA to 2captcha...")
        r = requests.post(
            "http://2captcha.com/in.php",
            data={
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
            },
            timeout=30,
        )
        if "OK|" not in r.text:
            log.error(f"2captcha submission failed: {r.text}")
            return None

        captcha_id = r.text.split("|")[1]
        log.info(f"CAPTCHA submitted, ID: {captcha_id}")

        for _ in range(30):
            time.sleep(5)
            r2 = requests.get(
                "http://2captcha.com/res.php",
                params={"key": self.api_key, "action": "get", "id": captcha_id},
                timeout=15,
            )
            if r2.text == "CAPCHA_NOT_READY":
                continue
            if "OK|" in r2.text:
                token = r2.text.split("|")[1]
                log.info("CAPTCHA solved")
                return token
            log.error(f"2captcha error: {r2.text}")
            return None

        log.error("Timeout waiting for 2captcha")
        return None
