"""Entry point for Pella.app — redirects to bot/bot.py."""
import subprocess
import sys

sys.exit(subprocess.call([sys.executable, "bot/bot.py"]))
