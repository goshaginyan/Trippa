"""Entry point for Pella.app — launches the Telegram bot."""
import subprocess
import sys
import os

# Ensure we run from the repo root regardless of working directory
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)

sys.exit(subprocess.call([sys.executable, "bot/bot.py"]))
