#!/usr/bin/env python3
"""
Facebook Account Creator – Main entry point.
Supports signup + post-creation verification (OK / NOT OK).
"""

import argparse
import sys
import yaml
import csv
import os
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from logger_utils import log
from account_gen import ProfileGenerator
from browser import FacebookBrowser
from captcha_solver import CaptchaSolver
from email_handler import get_email_handler


def load_config(path: str = "config.yaml") -> dict:
    """Load YAML configuration."""
    cfg_path = Path(path)
    if cfg_path.exists():
        with open(cfg_path, "r") as f:
            return yaml.safe_load(f) or {}
    log.warning(f"Config file {path} not found – using defaults")
    return {}


def save_accounts(accounts: List[Dict], filepath: str):
    """Export account list to CSV."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "#", "first_name", "last_name", "email", "password",
        "gender", "dob", "signup_status", "account_ok", "verification_reason"
    ]
    mode = "a" if path.exists() else "w"
    with open(path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        writer.writerows(accounts)

    log.info(f"Accounts appended to {path.resolve()}")


def print_summary(accounts: List[Dict]):
    """Print final account summary table with OK / NOT OK status."""
    print("\n" + "=" * 110)
    header = f"{'':>3} | {'Name':<18} | {'Email':<30} | {'Password':<14} | {'Gender':<5} | {'Signup':<8} | {'Status':<8}"
    print(header)
    print("-" * 110)

    ok_count = 0
    not_ok_count = 0
    signup_ok_count = 0

    for acc in accounts:
        num = acc['#']
        name = f"{acc['first_name']} {acc['last_name']}"[:18]
        email = acc['email'][:30]
        pwd = acc['password'][:14]
        gender = acc['gender'][:5]
        signup = "✓" if "success" in acc.get("signup_status", "").lower() else "✗"
        ok_status = acc.get("account_ok", "N/A")

        if ok_status == "TRUE":
            ok_display = "✓ OK"
            ok_count += 1
        elif ok_status == "FALSE":
            ok_display = "✗ NOT OK"
            not_ok_count += 1
        else:
            ok_display = "? UNKNOWN"

        if signup == "✓":
            signup_ok_count += 1

        print(f"{num:>3} | {name:<18} | {email:<30} | {pwd:<14} | {gender:<5} | {signup:<8} | {ok_display:<8}")

    # Detailed failure reasons
    failures = [
        a for a in accounts
        if a.get("account_ok") == "FALSE" or "success" not in a.get("signup_status", "").lower()
    ]
    if failures:
        print("\n── Failure Details ──────────────────────────────────────────────")
        for acc in failures:
            reason = acc.get("verification_reason", acc.get("signup_status", "Unknown"))
            print(f"  #{acc['#']} ({acc['email']}) → {reason}")

    print("=" * 110)
    print(f"Total: {len(accounts)}  |  Signup OK: {signup_ok_count}  |  "
          f"Account OK: {ok_count}  |  NOT OK: {not_ok_count}  |  "
          f"Unknown: {len(accounts) - ok_count - not_ok_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Facebook Account Creator – automated registration + verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main --count 5
  python -m src.main --count 10 --gender female
  python -m src.main --count 3 --email manual --password "MyPass123"
  python -m src.main --count 1 --headless --captcha-service 2captcha --captcha-key YOUR_KEY
  python -m src.main --count 5 --no-verify
  python -m src.main --verify-only --output accounts/created_accounts.csv
        """
    )

    parser.add_argument("--count", "-c", type=int, default=1,
                        help="Number of accounts to create (default: 1)")
    parser.add_argument("--gender", "-g", type=str, default="auto",
                        choices=["auto", "male", "female", "m", "f", "1", "2"],
                        help="Gender for all accounts (default: auto/random)")
    parser.add_argument("--password", "-p", type=str, default="",
                        help="Password for all accounts (default: auto-generated)")
    parser.add_argument("--email", "-e", type=str, default="auto",
                        choices=["auto", "manual"],
                        help="Email mode: 'auto' uses temp mail, 'manual' prompts")
    parser.add_argument("--email-backend", type=str, default="mail.tm",
                        choices=["mail.tm", "guerrilla"],
                        help="Temp mail backend (default: mail.tm)")
    parser.add_argument("--headless", action="store_true",
                        help="Run browser in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.set_defaults(headless=False)
    parser.add_argument("--proxy", type=str, default="",
                        help="Proxy URL (e.g. socks5://127.0.0.1:9050)")
    parser.add_argument("--captcha-service", type=str, default="manual",
                        choices=["manual", "2captcha", "anticaptcha"],
                        help="CAPTCHA solving service")
    parser.add_argument("--captcha-key", type=str, default="",
                        help="CAPTCHA service API key")
    parser.add_argument("--output", "-o", type=str, default="accounts/created_accounts.csv",
                        help="Output CSV file path")
    parser.add_argument("--config", type=str, default="config.yaml",
                        help="Path to YAML config file")
    parser.add_argument("--min-age", type=int, default=18,
                        help="Minimum age for generated profiles")
    parser.add_argument("--max-age", type=int, default=65,
                        help="Maximum age for generated profiles")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip post-creation account verification")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify existing accounts from CSV (no signup)")

    args = parser.parse_args()

    # ── Load config + CLI override ─────────────────────────────────────────
    cfg = load_config(args.config)
    count = args.count
    gender = args.gender if args.gender != "auto" else ""
    password = args.password if args.password else ""
    email_mode = args.email
    headless = args.headless or cfg.get("headless", False)
    proxy = args.proxy or cfg.get("proxy", "")
    captcha_service = args.captcha_service or cfg.get("captcha_service", "manual")
    captcha_key = args.captcha_key or cfg.get("captcha_api_key", "")
    email_backend = args.email_backend or cfg.get("email_backend", "mail.tm")
    output_file = args.output or cfg.get("output_file", "accounts/created_accounts.csv")
    min_age = args.min_age or cfg.get("min_age", 18)
    max_age = args.max_age or cfg.get("max_age", 65)
    do_verify = not args.no_verify
    verify_only = args.verify_only

    log.info("=" * 50)
    log.info("Facebook Account Creator v1.0.0")
    log.info(f"Accounts to create: {count}")
    log.info(f"Email mode: {email_mode} ({email_backend})")
    log.info(f"Gender: {gender or 'random'}")
    log.info(f"Password: {'auto-generated' if not password else 'user-provided'}")
    log.info(f"CAPTCHA: {captcha_service}")
    log.info(f"Headless: {headless}")
    log.info(f"Proxy: {proxy or 'none'}")
    log.info(f"Post-creation verification: {'ON' if do_verify else 'OFF'}")
    log.info("=" * 50)

    # ── Init components ────────────────────────────────────────────────────
    profile_gen = ProfileGenerator(min_age=min_age, max_age=max_age)
    captcha_solver = CaptchaSolver(service=captcha_service, api_key=captcha_key)

    results: List[Dict] = []

    # ── VERIFY-ONLY mode ──────────────────────────────────────────────────
    if verify_only:
        log.info("Verify-only mode – reading accounts from CSV...")
        csv_path = Path(output_file)
        if not csv_path.exists():
            log.error(f"CSV file not found: {output_file}")
            sys.exit(1)

        import csv as csv_mod
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                results.append({
                    "#": len(results) + 1,
                    "first_name": row.get("first_name", ""),
                    "last_name": row.get("last_name", ""),
                    "email": row.get("email", ""),
                    "password": row.get("password", ""),
                    "gender": row.get("gender", ""),
                    "dob": row.get("dob", ""),
                    "signup_status": row.get("signup_status", "N/A"),
                    "account_ok": "",
                    "verification_reason": "",
                })

        if not results:
            log.error("No accounts found in CSV")
            sys.exit(1)

        log.info(f"Loaded {len(results)} accounts for verification")

        browser = FacebookBrowser(
            headless=headless,
            proxy=proxy,
            captcha_solver=captcha_solver,
            email_backend=email_backend,
        )

        for acc in results:
            email = acc["email"]
            pwd = acc["password"]
            log.info(f"Verifying #{acc['#']}: {email}")

            try:
                browser.driver = None
                ver_result = browser.verify_account(email, pwd)
                acc["account_ok"] = ver_result["ok"]
                acc["verification_reason"] = ver_result["reason"]
                log.info(f"  → {'✓ OK' if ver_result['ok']=='TRUE' else '✗ NOT OK'}: {ver_result['reason']}")
            except Exception as e:
                acc["account_ok"] = "FALSE"
                acc["verification_reason"] = f"Verification error: {e}"
                log.error(f"  → Error: {e}")
            finally:
                browser.close()

            if results.index(acc) < len(results) - 1:
                time.sleep(2)

        save_accounts(results, output_file)
        print_summary(results)
        return

    # ── NORMAL SIGNUP MODE ────────────────────────────────────────────────
    browser = FacebookBrowser(
        headless=headless,
        proxy=proxy,
        captcha_solver=captcha_solver,
        email_backend=email_backend,
    )

    try:
        for i in range(1, count + 1):
            log.info(f"\n{'─'*50}")
            log.info(f"Account {i}/{count}")
            log.info(f"{'─'*50}")

            # ── Get email ─────────────────────────────────────────────────
            if email_mode == "manual":
                email_input = input(f"  [{i}/{count}] Enter email address: ").strip()
                while not email_input:
                    email_input = input("  Email cannot be empty: ").strip()
            else:
                email_input = ""

            # ── Generate profile ──────────────────────────────────────────
            profile = profile_gen.generate(
                email=email_input if email_input else "",
                password=password,
                gender=gender,
                custom_email=email_input if email_mode == "manual" else "",
            )

            gender_label = "Male" if profile.gender == "2" else "Female"
            log.info(f"Profile: {profile.first_name} {profile.last_name} | "
                     f"{profile.email} | {gender_label} | "
                     f"{profile.dob_year}-{profile.dob_month}-{profile.dob_day}")

            # ── Execute signup ────────────────────────────────────────────
            browser.driver = None
            success, signup_msg = browser.signup(profile)
            browser.close()

            signup_status_str = "Success" if success else "Failed"

            # ── Verify the account ────────────────────────────────────────
            account_ok = ""
            verify_reason = ""
            if do_verify and success:
                log.info(f"Verifying account #{i} (logging in to check status)...")
                try:
                    browser.driver = None
                    ver_result = browser.verify_account(profile.email, profile.password)
                    browser.close()
                    account_ok = ver_result["ok"]
                    verify_reason = ver_result["reason"]
                    if account_ok == "TRUE":
                        log.info(f"  ✅ Account #{i} is OK – active and unrestricted")
                    else:
                        log.info(f"  ❌ Account #{i} is NOT OK – {verify_reason}")
                except Exception as e:
                    account_ok = "FALSE"
                    verify_reason = f"Verification error: {e}"
                    log.error(f"  Verification failed: {e}")
            elif not success:
                account_ok = "FALSE"
                verify_reason = "Signup did not complete"
            else:
                account_ok = "UNVERIFIED"
                verify_reason = "Verification skipped (--no-verify)"

            results.append({
                "#": i,
                "first_name": profile.first_name,
                "last_name": profile.last_name,
                "email": profile.email,
                "password": profile.password,
                "gender": gender_label,
                "dob": f"{profile.dob_year}-{profile.dob_month.zfill(2)}-{profile.dob_day.zfill(2)}",
                "signup_status": signup_status_str,
                "account_ok": account_ok,
                "verification_reason": verify_reason,
            })

            if account_ok == "TRUE":
                status_icon = "✅ OK"
            elif account_ok == "FALSE":
                status_icon = "❌ NOT OK"
            else:
                status_icon = f"? {account_ok}"

            log.info(f"→ Account {i}: Signup {'✓' if success else '✗'} | Status: {status_icon} | {verify_reason or signup_msg}")

            if i < count:
                delay = 3 + (i % 5)
                log.info(f"Waiting {delay}s before next account...")
                time.sleep(delay)

    except KeyboardInterrupt:
        log.warning("\nUser interrupted – generating summary...")
    except Exception as e:
        log.error(f"Fatal error: {e}")
        import traceback
        log.debug(traceback.format_exc())
    finally:
        browser.close()

    if results:
        save_accounts(results, output_file)
        print_summary(results)
        log.info(f"Account list saved to {output_file}")
    else:
        log.warning("No accounts were processed")


if __name__ == "__main__":
    main()
