import os
from pathlib import Path

# Load .env file if present (no extra dependency)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

BOT_TOKEN = os.environ.get("TRIPPA_BOT_TOKEN", "")
DATA_DIR = os.environ.get("TRIPPA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
