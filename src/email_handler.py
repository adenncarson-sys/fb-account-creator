#!/usr/bin/env python3
"""
Email handler – disposable email inbox management.
Supports Mail.tm (free REST API) and Guerrilla Mail (legacy).
"""

import requests
import json
import time
import re
import uuid
from typing import Optional
from logger_utils import log


class MailTMHandler:
    """Mail.tm API wrapper – free, no API key required."""

    BASE = "https://api.mail.tm"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        self.account_id = None
        self.token = None
        self.email_address = None

    def _get_domains(self) -> list:
        r = self.session.get(f"{self.BASE}/domains", timeout=10)
        r.raise_for_status()
        return [d["domain"] for d in r.json()["hydra:member"]]

    def create_inbox(self) -> str:
        """Create a new temporary inbox and return the email address."""
        domains = self._get_domains()
        if not domains:
            raise RuntimeError("No domains available from Mail.tm")

        domain = domains[0]
        local = uuid.uuid4().hex[:12]
        password = uuid.uuid4().hex[:16]
        self.email_address = f"{local}@{domain}"

        payload = {"address": self.email_address, "password": password}
        r = self.session.post(f"{self.BASE}/accounts", json=payload, timeout=10)
        if r.status_code == 201:
            data = r.json()
            self.account_id = data["id"]
            self.token = data["token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            log.info(f"Temp inbox created: {self.email_address}")
            return self.email_address

        # fallback to second domain
        if len(domains) > 1:
            domain = domains[1]
            self.email_address = f"{local}@{domain}"
            payload = {"address": self.email_address, "password": password}
            r = self.session.post(f"{self.BASE}/accounts", json=payload, timeout=10)
            if r.status_code == 201:
                data = r.json()
                self.account_id = data["id"]
                self.token = data["token"]
                self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                log.info(f"Temp inbox created: {self.email_address}")
                return self.email_address

        raise RuntimeError(f"Failed to create Mail.tm inbox: {r.status_code}")

    def wait_for_message(self, timeout: int = 60, poll_interval: int = 3) -> Optional[str]:
        """Poll inbox until a message arrives; returns body text."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.session.get(f"{self.BASE}/messages", timeout=10)
            if r.status_code == 200:
                msgs = r.json().get("hydra:member", [])
                if msgs:
                    msg_id = msgs[-1]["id"]
                    r2 = self.session.get(f"{self.BASE}/messages/{msg_id}", timeout=10)
                    if r2.status_code == 200:
                        html = r2.json().get("html", [""])[0]
                        text = re.sub(r"<[^>]+>", "", html).strip()
                        log.info("Email received from Facebook")
                        return text
            time.sleep(poll_interval)
        log.warning("Timeout waiting for confirmation email")
        return None

    def get_confirmation_link(self, text: str) -> Optional[str]:
        urls = re.findall(r'https?://[^\s"\']+(?:fb\.me|facebook\.com/confirm[^\s"\']*)', text)
        if urls:
            return urls[0]
        urls = re.findall(r'https?://[^\s"\']+', text)
        for u in urls:
            if "confirm" in u.lower() or "facebook" in u.lower():
                return u
        return None

    def cleanup(self):
        if self.account_id and self.token:
            try:
                self.session.delete(f"{self.BASE}/accounts/{self.account_id}", timeout=10)
                log.debug(f"Temp inbox {self.email_address} deleted")
            except Exception:
                pass


class GuerrillaMailHandler:
    """Guerrilla Mail API wrapper."""

    BASE = "http://api.guerrillamail.com/ajax.php"

    def __init__(self):
        self.session = requests.Session()
        self.email_address = None
        self.sid_token = None

    def create_inbox(self) -> str:
        params = {"f": "get_email_address", "ip": "127.0.0.1", "agent": "HackerAI-FB-Creator"}
        r = self.session.get(self.BASE, params=params, timeout=10)
        data = r.json()
        self.email_address = data["email_addr"]
        self.sid_token = data["sid_token"]
        log.info(f"Temp inbox created: {self.email_address}")
        return self.email_address

    def wait_for_message(self, timeout: int = 60, poll_interval: int = 3) -> Optional[str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            params = {"f": "get_email_list", "sid_token": self.sid_token,
                      "ip": "127.0.0.1", "agent": "HackerAI-FB-Creator"}
            r = self.session.get(self.BASE, params=params, timeout=10)
            data = r.json()
            emails = data.get("list", [])
            if emails:
                mail_id = emails[0]["mail_id"]
                params2 = {"f": "fetch_email", "sid_token": self.sid_token,
                           "email_id": mail_id, "ip": "127.0.0.1", "agent": "HackerAI-FB-Creator"}
                r2 = self.session.get(self.BASE, params=params2, timeout=10)
                body = r2.json().get("mail_body", "")
                text = re.sub(r"<[^>]+>", "", body).strip()
                log.info("Email received from Facebook")
                return text
            time.sleep(poll_interval)
        log.warning("Timeout waiting for confirmation email")
        return None

    def get_confirmation_link(self, text: str) -> Optional[str]:
        urls = re.findall(r'https?://[^\s"\']+(?:fb\.me|facebook\.com/confirm[^\s"\']*)', text)
        if urls:
            return urls[0]
        urls = re.findall(r'https?://[^\s"\']+', text)
        for u in urls:
            if "confirm" in u.lower() or "facebook" in u.lower():
                return u
        return None

    def cleanup(self):
        pass


def get_email_handler(backend: str = "mail.tm"):
    """Factory – return the appropriate email handler."""
    if backend == "guerrilla":
        return GuerrillaMailHandler()
    return MailTMHandler()
