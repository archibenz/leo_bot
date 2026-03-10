#!/usr/bin/env bash
set -euo pipefail

python_bin="python3"
if command -v python >/dev/null 2>&1; then
  python_bin="python"
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  "$python_bin" -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing required packages..."
pip install -r requirements.txt

# Create .env template if it doesn't exist and only copy when missing
if [ ! -f ".env.example" ]; then
  echo "Creating .env.example template..."
  cat <<'ENV' > .env.example
BOT_TOKEN=your_bot_token_here
SHEET_ID=your_google_sheet_id_here
# Optional: comma-separated list of admin Telegram user IDs for support routing
ADMIN_IDS=1358870721,1023066249,206441957
# Optional: custom path to Google credentials file
# GOOGLE_APPLICATION_CREDENTIALS=credentials.json
ENV
fi

if [ ! -f ".env" ]; then
  echo ".env not found. Creating it from .env.example (existing tokens will remain untouched in future runs)..."
  cp .env.example .env
  echo "Please update .env file with your actual credentials."
else
  echo "Existing .env detected; leaving it unchanged."
fi

# Create a placeholder for Google API credentials
if [ ! -f "credentials.json" ]; then
  cat <<'MSG'
IMPORTANT: You need to create a credentials.json file with your Google API credentials.
Visit https://console.developers.google.com/ to create a service account and download the JSON key.
MSG
fi

echo "Setup completed successfully!"
echo "To run the bot, use: source venv/bin/activate && python main.py"
