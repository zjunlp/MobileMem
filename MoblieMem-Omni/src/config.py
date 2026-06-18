"""
Centralized runtime configuration for the pipeline.

Every environment variable is read here exactly once, each with a safe default,
so importing any pipeline module never crashes - even without a ``.env`` file.
Modules should read settings from this module instead of calling ``os.getenv``
directly, which keeps configuration in one place and avoids import-time failures.
"""

import os
import sys

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# .env loading (idempotent). Looks for ``src/.env`` next to this file.
# ---------------------------------------------------------------------------
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)

_ENV_PATH = os.path.join(SRC_DIR, '.env')
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH, override=True)


# ---------------------------------------------------------------------------
# Console encoding: make Windows consoles print UTF-8 without garbling.
# Centralized here so individual modules don't each reconfigure stdout/stderr.
# ---------------------------------------------------------------------------
def _ensure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


_ensure_utf8_console()


# ---------------------------------------------------------------------------
# Typed env helpers (empty string is treated as "unset")
# ---------------------------------------------------------------------------
def _get_str(key: str, default: str) -> str:
    val = os.getenv(key)
    return val if val not in (None, '') else default


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val in (None, ''):
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val in (None, ''):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val in (None, ''):
        return default
    return val.strip().lower() in ('1', 'true', 'yes', 'on')


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROMPTS_DIR = os.path.join(PROJECT_ROOT, 'prompts')
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, 'templates')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
LOG_DIR = os.path.join(OUTPUT_DIR, 'logs')


# ---------------------------------------------------------------------------
# Text LLM API (OpenAI-compatible)
# ---------------------------------------------------------------------------
OPENAI_API_KEY = _get_str('OPENAI_API_KEY', '')
OPENAI_BASE_URL = _get_str('OPENAI_BASE_URL', 'https://api.openai.com/v1')
# Fallback model used by llm_request() when a caller does not pass an explicit
# model (e.g. the legacy stage4 CLI path).
OPENAI_MODEL = _get_str('OPENAI_MODEL', 'gpt-4o')
OPENAI_MODEL_CN = _get_str('OPENAI_MODEL_CN', 'deepseek-chat')
# Text model returned by get_text_llm_model() — selected per persona language and
# passed explicitly by every stage. Independent of the OPENAI_MODEL fallback
# above. Both default to the historical hardcoded value ("gpt-5.1") so behavior
# is unchanged out of the box; override either via the environment.
TEXT_LLM_MODEL = _get_str('TEXT_LLM_MODEL', 'gpt-5.1')
TEXT_LLM_MODEL_CN = _get_str('TEXT_LLM_MODEL_CN', TEXT_LLM_MODEL)
OPENAI_MAX_TOKENS = _get_int('OPENAI_MAX_TOKENS', 16384)
OPENAI_TEMPERATURE = _get_float('OPENAI_TEMPERATURE', 0.5)
OPENAI_TIMEOUT = _get_int('OPENAI_TIMEOUT', 180)

# Retry policy for transient API errors
RETRY_TIMES = _get_int('RETRY_TIMES', 30)
WAIT_TIME_LOWER = _get_int('WAIT_TIME_LOWER', 10)
WAIT_TIME_UPPER = _get_int('WAIT_TIME_UPPER', 30)


# ---------------------------------------------------------------------------
# Image generation API (DMXAPI)
# ---------------------------------------------------------------------------
DMX_API_KEY = _get_str('DMX_API_KEY', '')
DMX_BASE_URL = _get_str('DMX_BASE_URL', 'https://www.dmxapi.cn/v1')
DMX_GENERATION_URL = _get_str('DMX_GENERATION_URL', 'https://www.dmxapi.cn/v1/images/generations')
DMX_EDIT_URL = _get_str('DMX_EDIT_URL', 'https://www.dmxapi.cn/v1/images/edits')
DMX_CHINESE_GENERATION_MODEL = _get_str('DMX_CHINESE_GENERATION_MODEL', 'doubao-seedream-4-5-251128')
DMX_CHINESE_EDIT_MODEL = _get_str('DMX_CHINESE_EDIT_MODEL', DMX_CHINESE_GENERATION_MODEL)
DMX_CHINESE_EDIT_PROMPT_MAX = _get_int('DMX_CHINESE_EDIT_PROMPT_MAX', 1000)


# ---------------------------------------------------------------------------
# Image generation API (OpenRouter, Gemini image model)
# ---------------------------------------------------------------------------
# Images are generated via OpenRouter's Gemini image model by default. OpenRouter
# serves images through the chat endpoint with modalities=["image", "text"]
# (not /images/generations), so the backend uses a dedicated code path. Set
# IMAGE_PROVIDER=dmx to use the legacy DMX endpoints above instead.
IMAGE_PROVIDER = _get_str('IMAGE_PROVIDER', 'openrouter').strip().lower()
OPENROUTER_API_KEY = _get_str('OPENROUTER_API_KEY', OPENAI_API_KEY)
OPENROUTER_BASE_URL = _get_str('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
OPENROUTER_IMAGE_MODEL = _get_str('OPENROUTER_IMAGE_MODEL', 'google/gemini-2.5-flash-image')
# Optional HTTP/HTTPS proxy for image API calls; configure via the environment.
# Empty disables explicit proxying.
IMAGE_HTTP_PROXY = _get_str('IMAGE_HTTP_PROXY', '')
# Downscale input images to this longest side to keep request bodies small.
IMAGE_MAX_INPUT_SIDE = _get_int('IMAGE_MAX_INPUT_SIDE', 1024)
# Retry count for transient image API errors; kept separate from RETRY_TIMES.
IMAGE_RETRY_TIMES = _get_int('IMAGE_RETRY_TIMES', 30)


# ---------------------------------------------------------------------------
# LLM call logging
# ---------------------------------------------------------------------------
LLM_CALL_LOGS_DIR = _get_str('LLM_CALL_LOGS_DIR', os.path.join(OUTPUT_DIR, 'llm_call_logs'))
LLM_CALL_LOGS_ENABLED = _get_bool('LLM_CALL_LOGS_ENABLED', True)


# ---------------------------------------------------------------------------
# Networking: bypass the system proxy by default to avoid SSL handshake issues.
# ---------------------------------------------------------------------------
os.environ.setdefault('NO_PROXY', '*')
