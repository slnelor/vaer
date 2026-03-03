import os

DEFAULT_MODEL = os.getenv("VAER_MODEL", "openai/gpt-oss-120b")
DEFAULT_PROVIDER = os.getenv("VAER_PROVIDER", "openai")
DEFAULT_AGENT_MODE = os.getenv("VAER_AGENT_MODE", "code")
SESSION_SCOPE = os.getenv("VAER_SESSION_SCOPE", "project")
REQUEST_TIMEOUT_SEC = float(os.getenv("VAER_TIMEOUT_SEC", "25"))
MAX_PARALLEL_REQUESTS = int(os.getenv("VAER_MAX_PARALLEL", "4"))
SPINNER_INTERVAL_MS = int(os.getenv("VAER_SPINNER_MS", "120"))
LOG_PATH = os.getenv("VAER_LOG_PATH", "/tmp/vaer.log")
TMP_DIR_NAME = os.getenv("VAER_TMP_DIR", "tmp")
TOGGLE_KEY_INSERT = "<C-t>"
TOGGLE_KEY_NORMAL = "<C-t>"
