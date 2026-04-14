"""Load configuration from environment."""

import os

import truststore
from dotenv import load_dotenv

truststore.inject_into_ssl()

load_dotenv()


def _get(key: str) -> str | None:
    v = os.getenv(key)
    if v is not None and v.strip() == "":
        return None
    return v


EIA_API_KEY = _get("EIA_API_KEY")
FRED_API_KEY = _get("FRED_API_KEY")
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_BASE_URL = _get("OPENAI_BASE_URL")
OPENAI_API_VERSION = _get("OPENAI_API_VERSION") or "2024-12-01-preview"
OPENAI_MODEL = _get("OPENAI_MODEL") or "gpt-4.1-nano"
