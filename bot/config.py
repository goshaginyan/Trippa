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

# On Railway, volumes are mounted at a fixed path (e.g. /data).
# Default to /data when running on Railway, otherwise use local bot/data/.
_default_data_dir = os.path.join(os.path.dirname(__file__), "data")
if os.environ.get("RAILWAY_ENVIRONMENT") and os.path.isdir("/data"):
    _default_data_dir = "/data"

DATA_DIR = os.environ.get("TRIPPA_DATA_DIR", _default_data_dir)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ALLOWED_USER_IDS = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}
