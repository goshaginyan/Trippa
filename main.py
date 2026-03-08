"""Entry point — redirects to bot/main.py."""
import subprocess
import sys

sys.exit(subprocess.call([sys.executable, "bot/main.py"]))
