import os

BOT_TOKEN = os.environ.get("TRIPPA_BOT_TOKEN", "")
DATA_DIR = os.environ.get("TRIPPA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
