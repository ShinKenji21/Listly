"""Settings from .env and the shared API client."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("META_MODEL", "muse-spark-1.3")
BASE_URL = os.getenv("META_BASE_URL", "https://api.meta.ai/v1")
CACHE_DIR = Path("cache")
MAX_IMAGE_SIDE = 1024  # bigger images cost more credits and don't help identification
# Demo mode returns a sample answer instead of calling the API: lets us test the UI
# and rehearse the demo without spending credits.
DEMO_MODE = os.getenv("LISTLY_DEMO") == "1"


def has_api_key() -> bool:
    # The placeholder from .env.example counts as "no key", so new users get the setup hint.
    return os.getenv("META_API_KEY", "") not in ("", "your-key-here")


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    # Created on first use, not at import: OpenAI() raises if the key is missing,
    # which would crash the app before it can show a friendly message.
    # The Meta Model API is OpenAI-compatible, so the openai SDK works with a custom base URL.
    return OpenAI(api_key=os.getenv("META_API_KEY"), base_url=BASE_URL)
