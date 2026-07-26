#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Termux Setup Script for Facebook Account Creator
# Run this ONCE after cloning the repo on Termux
# ──────────────────────────────────────────────────────────────────────────────

set -e

echo "=========================================="
echo "  Facebook Account Creator – Termux Setup"
echo "=========================================="
echo ""

# ── 1. Update packages ─────────────────────────────────────────────────────
echo "[1/6] Updating Termux packages..."
pkg update -y && pkg upgrade -y

# ── 2. Add required repositories ───────────────────────────────────────────
echo "[2/6] Adding Termux repositories..."
pkg install -y tur-repo x11-repo

# ── 3. Install Chromium and dependencies ──────────────────────────────────
echo "[3/6] Installing Chromium browser (~300MB download)..."
pkg install -y chromium xorg-server-xvfb

# ── 4. Install Python and pip ─────────────────────────────────────────────
echo "[4/6] Installing Python..."
pkg install -y python python-pip

# ── 5. Install Python packages ────────────────────────────────────────────
echo "[5/6] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# ── 6. Verify installation ────────────────────────────────────────────────
echo "[6/6] Verifying installation..."

# Check chromium
if command -v chromium-browser &> /dev/null; then
    CHROME_VER=$(chromium-browser --version 2>/dev/null || echo "found")
    echo "  ✓ Chromium: $CHROME_VER"
else
    echo "  ✗ Chromium not found at expected path"
    echo "    Expected: /data/data/com.termux/files/usr/bin/chromium-browser"
fi

# Check chromedriver
CHROMEDRIVER_PATH="/data/data/com.termux/files/usr/lib/chromium/chromedriver"
if [ -f "$CHROMEDRIVER_PATH" ]; then
    echo "  ✓ Chromedriver: $CHROMEDRIVER_PATH"
else
    echo "  ⚠ Chromedriver not found – undetected-chromedriver will handle it"
fi

# Check Python packages
python -c "import undetected_chromedriver, selenium, faker, yaml, colorama; print('  ✓ All Python packages installed')" 2>/dev/null || {
    echo "  ✗ Some Python packages failed – try: pip install -r requirements.txt"
}

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "Quick test:"
echo "  python -m src.main --count 1 --headless"
echo ""
echo "For headed (GUI) mode:"
echo "  pkg install tigervnc"
echo "  vncserver :1"
echo "  DISPLAY=:1 python -m src.main --count 1"
echo ""
