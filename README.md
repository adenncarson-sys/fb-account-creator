# Facebook Account Creator

> **Automated Facebook account registration + verification tool for authorized security assessments.**

## ⚠️ Legal

You must have **explicit written permission** from the account owner / platform owner before using this. Unauthorized use may violate Facebook's Terms of Service and applicable laws.

## Features

- **Bulk creation** – configurable number of accounts
- **Auto temp email** – disposable inbox via Mail.tm or Guerrilla Mail (free, no API key)
- **Manual email** – supply your own emails
- **Auto / manual gender & password** – fully random or user-defined
- **Browser automation** – undetected-chromedriver with fingerprint spoofing
- **Account verification** – logs in after creation and checks if the account is **OK** (active) or **NOT OK** (suspended, disabled, checkpointed, under review)
- **CAPTCHA solving** – manual mode or 2captcha / Anti-Captcha integration
- **Proxy support** – SOCKS5/HTTP proxies
- **Real-time logging** – colored console + timestamped log files
- **CSV export** – account number, name, email, password, gender, DOB, signup status, OK/NOT OK, reason
- **Termux auto-detection** – detects Android/Termux and sets the correct Chromium paths and flags

## Termux Setup (One Command)

```bash
pkg update && pkg upgrade -y
pkg install git -y
git clone https://github.com/YOUR_USER/fb-account-creator.git
cd fb-account-creator
chmod +x termux_setup.sh
./termux_setup.sh
