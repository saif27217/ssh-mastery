#!/bin/bash
# Pi-Telegram Quick Start Script

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pi-Telegram Setup Assistant"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Check if pi is installed
if ! command -v pi &> /dev/null; then
    echo "❌ Error: pi is not installed or not in PATH"
    echo "Please install pi first: https://pi.dev"
    exit 1
fi

echo "✅ Pi is installed ($(pi --version))"
echo

# Check if pi-telegram is installed
echo "Checking pi-telegram installation..."
if pi list | grep -q "pi-telegram"; then
    echo "✅ pi-telegram is installed"
else
    echo "❌ pi-telegram is not installed"
    echo "Please run: pi install ~/pi-telegram"
    exit 1
fi
echo

# Create telegram config directory
CONFIG_DIR="$HOME/.pi/agent"
mkdir -p "$CONFIG_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1: Create Telegram Bot"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "Instructions:"
echo "  1. Open Telegram and search for @BotFather"
echo "  2. Send: /newbot"
echo "  3. Choose a name (e.g., 'My Pi Bot')"
echo "  4. Choose a username (e.g., 'my_pi_bot')"
echo "  5. Copy the bot token (123456:ABCDEF...)"
echo

read -p "Press Enter when you have your bot token..."
echo

# Check if config already exists
if [ -f "$CONFIG_DIR/telegram.json" ]; then
    echo "ℹ️  Configuration file already exists:"
    cat "$CONFIG_DIR/telegram.json" | head -5
    echo
    read -p "Do you want to reconfigure? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Using existing configuration."
    fi
fi

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2: Starting Pi Interactive Session"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "Next steps in Pi session:"
echo "  1. Type: /telegram-setup"
echo "  2. Paste your bot token"
echo "  3. Type: /telegram-connect"
echo
echo "Then in Telegram:"
echo "  1. Find your bot (@your_bot_username)"
echo "  2. Send: /start"
echo "  3. Start chatting!"
echo
echo "Commands:"
echo "  /telegram-status     - Show bridge status"
echo "  /telegram-disconnect - Stop the bridge"
echo "  /help                - Show help in Pi"
echo

read -p "Ready to start Pi? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pi
else
    echo "Setup complete. Run 'pi' when you're ready."
fi
