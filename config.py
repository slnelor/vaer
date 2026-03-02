from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    api_key_env: str


PROVIDER_SERVERS = {
    "openai": ProviderConfig(
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "openrouter": ProviderConfig(
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
}


DEFAULT_MODEL = os.getenv("VAER_MODEL", "openai/gpt-4.1-mini")
REQUEST_TIMEOUT_SEC = float(os.getenv("VAER_TIMEOUT_SEC", "25"))
MAX_PARALLEL_REQUESTS = int(os.getenv("VAER_MAX_PARALLEL", "4"))
SPINNER_INTERVAL_MS = int(os.getenv("VAER_SPINNER_MS", "120"))
LOG_PATH = os.getenv("VAER_LOG_PATH", "/tmp/vaer.log")
TMP_DIR_NAME = os.getenv("VAER_TMP_DIR", "tmp")
TOGGLE_KEY_INSERT = "<C-t>"
TOGGLE_KEY_NORMAL = "<C-t>"
