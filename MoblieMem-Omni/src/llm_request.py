import os
import json
import logging
import re
import threading
from typing import Dict, List, Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
    before_sleep_log
)
from openai import OpenAI

import config

# Module logger. Handlers are attached lazily via setup_llm_logging() rather than
# calling logging.basicConfig() at import time, which would hijack the root logger
# and truncate a log file merely as a side effect of importing this module.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_log_configured = False


def setup_llm_logging(log_file: str = 'llm_caller.log', level: int = logging.DEBUG) -> None:
    """Optionally route this module's debug logs to a file. Safe to call repeatedly."""
    global _log_configured
    if _log_configured:
        return
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    _log_configured = True


MODEL_PRICING = {
    'gpt-4o': {
        'input': 2.50,
        'output': 10.00
    },
    'gpt-4o-2024-05-13': {
        'input': 5.00,
        'output': 15.00
    },
    'gpt-4o-2024-08-06': {
        'input': 2.50,
        'output': 10.00
    },
    'gpt-4o-2024-11-20': {
        'input': 2.50,
        'output': 10.00
    },
    'gpt-4o-mini': {
        'input': 0.15,
        'output': 0.60
    }
}


def calculate_cumulative_cost(previous_cost: Optional[Dict], current_cost: Dict) -> Dict:
    
    result = {
        "current_stage": current_cost,
        "cumulative": {
            "input_tokens": current_cost.get("input_tokens", 0) or 0,
            "output_tokens": current_cost.get("output_tokens", 0) or 0,
            "total_tokens": current_cost.get("total_tokens", 0) or 0,
            "total_cost_usd": current_cost.get("total_cost_usd", 0) or 0
        }
    }
    
    if previous_cost and isinstance(previous_cost, dict):

        if "cumulative" in previous_cost:
            prev_cumulative = previous_cost["cumulative"]
        elif "current_stage" in previous_cost:
            prev_cumulative = previous_cost["current_stage"]
        else:
            prev_cumulative = previous_cost
        
        if prev_cumulative:
            result["cumulative"]["input_tokens"] += prev_cumulative.get("input_tokens", 0) or 0
            result["cumulative"]["output_tokens"] += prev_cumulative.get("output_tokens", 0) or 0
            result["cumulative"]["total_tokens"] += prev_cumulative.get("total_tokens", 0) or 0
            result["cumulative"]["total_cost_usd"] += prev_cumulative.get("total_cost_usd", 0) or 0
    
    if result["cumulative"]["total_cost_usd"]:
        result["cumulative"]["total_cost_usd"] = round(result["cumulative"]["total_cost_usd"], 6)
    
    return result


def _repair_json_string(json_str: str) -> str:
    """
    Try to repair common JSON formatting issues returned by the LLM:
    1. Remove JavaScript-style single-line comments (// ...)
    2. Remove multi-line comments (/* ... */)
    3. Remove trailing commas (extra comma before ] or })
    4. Repair truncated JSON (try to close missing brackets)
    """
    repaired = json_str

    # 1. Remove single-line comments // ... (without affecting URLs inside strings such as http://)
    #    Strategy: only remove comment lines that start with // or follow a comma/bracket
    repaired = re.sub(r'(?m)^\s*//.*$', '', repaired)
    # Remove end-of-line comments (// comments outside of quotes)
    repaired = re.sub(r'(?<=["\d\]\}\s]),?\s*//[^\n]*', '', repaired)

    # 2. Remove multi-line comments /* ... */
    repaired = re.sub(r'/\*[\s\S]*?\*/', '', repaired)

    # 3. Remove trailing commas: ,] or ,} (possibly with whitespace in between)
    repaired = re.sub(r',\s*([\]\}])', r'\1', repaired)

    return repaired.strip()


def _try_fix_truncated_json(json_str: str) -> Optional[str]:
    """
    Try to repair truncated JSON by closing missing ] and }.
    Returns the repaired string, or None if it cannot be repaired.
    """
    # Count unclosed brackets
    stack = []
    in_string = False
    escape = False

    for ch in json_str:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()

    if not stack:
        return None  # brackets are balanced, no repair needed

    # Remove the last possibly incomplete element (truncated object/value)
    # Find the last complete }, ] or string value
    truncated = json_str.rstrip()
    # If the last char is not one of } ] " digit true false null, try to roll back to the previous complete element
    if truncated and truncated[-1] not in ('}', ']', '"', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'e', 'l'):
        # Search backwards for the last } or ] or "
        last_valid = max(truncated.rfind('}'), truncated.rfind(']'), truncated.rfind('"'))
        if last_valid > 0:
            truncated = truncated[:last_valid + 1]

    # Remove a trailing comma at the end
    truncated = re.sub(r',\s*$', '', truncated)

    # Close the missing brackets
    closing = ''
    for bracket in reversed(stack):
        if bracket == '{':
            closing += '}'
        elif bracket == '[':
            closing += ']'

    return truncated + closing


def _extract_json_from_content(content: str, markers: List[str]) -> Dict:
    
    json_content = content

    for marker in markers:
        if marker in json_content:
            parts = json_content.split(marker, 1)
            if len(parts) > 1:
                json_content = parts[1].strip()
                break

    if '```json' in json_content:
        start_idx = json_content.find('```json') + 7
        end_idx = json_content.rfind('```')
        if end_idx > start_idx:
            json_content = json_content[start_idx:end_idx].strip()
    elif '```' in json_content:
        start_idx = json_content.find('```') + 3
        end_idx = json_content.rfind('```')
        if end_idx > start_idx:
            json_content = json_content[start_idx:end_idx].strip()

    # Handle JSON arrays starting with [
    stripped = json_content.lstrip()
    if stripped.startswith('[') and ']' in json_content:
        start_idx = json_content.find('[')
        end_idx = json_content.rfind(']') + 1
        if end_idx > start_idx:
            json_content = json_content[start_idx:end_idx].strip()
    elif '{' in json_content and '}' in json_content:
        start_idx = json_content.find('{')
        end_idx = json_content.rfind('}') + 1
        if end_idx > start_idx:
            json_content = json_content[start_idx:end_idx].strip()
    elif '{' in json_content:
        # JSON may be truncated (only { without }), extract from the first {
        start_idx = json_content.find('{')
        json_content = json_content[start_idx:].strip()

    # First attempt: parse directly
    try:
        parsed_json = json.loads(json_content)
        logger.debug("Successfully parsed JSON")
        return parsed_json
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing error: {e}, trying repair...")

    # Second attempt: parse after repairing common issues (comments, trailing commas)
    repaired = _repair_json_string(json_content)
    try:
        parsed_json = json.loads(repaired)
        logger.info("Successfully parsed JSON after repair (comments/trailing commas)")
        return parsed_json
    except json.JSONDecodeError as e:
        logger.warning(f"JSON still invalid after basic repair: {e}, trying truncation fix...")

    # Third attempt: repair truncated JSON
    fixed = _try_fix_truncated_json(repaired)
    if fixed:
        try:
            parsed_json = json.loads(fixed)
            logger.info("Successfully parsed JSON after truncation fix")
            return parsed_json
        except json.JSONDecodeError as e:
            logger.warning(f"JSON still invalid after truncation fix: {e}")

    # Fourth attempt: regex extraction (supports both arrays and objects)
    for json_pattern in [r'(\[[\s\S]*\])', r'({[\s\S]*})']:
        match = re.search(json_pattern, json_content)
        if match:
            try:
                potential_json = match.group(1)
                potential_repaired = _repair_json_string(potential_json)
                parsed_json = json.loads(potential_repaired)
                logger.info("Successfully extracted and repaired JSON through regex")
                return parsed_json
            except json.JSONDecodeError:
                continue
    
    raise ValueError(f"Failed to parse JSON from content: {json_content[:200]}...")


def _calculate_cost(model: str, usage: Optional[Any]) -> Dict:

    if usage is None:
        logger.warning("No usage information available in API response")
        return {
            "input_tokens": None, "output_tokens": None, "total_tokens": None, "model": model,
            "input_cost_usd": None, "output_cost_usd": None, "total_cost_usd": None,
            "pricing_available": False, "note": "Usage information not available"
        }
    
    usage_dict = usage.model_dump()
    input_tokens = usage_dict.get('prompt_tokens', 0)
    output_tokens = usage_dict.get('completion_tokens', 0)
    
    cost_info = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "model": model
    }
    
    if model in MODEL_PRICING:
        pricing = MODEL_PRICING[model]
        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']
        total_cost = input_cost + output_cost
        
        cost_info.update({
            "input_cost_usd": round(input_cost, 6),
            "output_cost_usd": round(output_cost, 6),
            "total_cost_usd": round(total_cost, 6),
            "pricing_available": True
        })
    else:
        cost_info.update({
            "input_cost_usd": None, "output_cost_usd": None, "total_cost_usd": None,
            "pricing_available": False, "note": f"Pricing not available for model: {model}"
        })
    
    return cost_info


def get_text_llm_model(is_chinese: bool) -> str:
    """Return the text LLM model name for the given persona language.

    Reads :data:`config.TEXT_LLM_MODEL_CN` for Chinese personas and
    :data:`config.TEXT_LLM_MODEL` for everyone else. Both default to the
    historical hardcoded value (``"gpt-5.1"``), so behavior is unchanged out of
    the box while allowing each to be overridden via the environment.
    """
    return config.TEXT_LLM_MODEL_CN if is_chinese else config.TEXT_LLM_MODEL


# ============================================================================
# LLM call logging framework
# ============================================================================

_log_context = threading.local()

# LLM call-logging settings (centralized in config).
LLM_CALL_LOGS_DIR = config.LLM_CALL_LOGS_DIR
LLM_CALL_LOGS_ENABLED = config.LLM_CALL_LOGS_ENABLED

# Write lock to prevent multiple threads from writing the same file at once
_log_write_lock = threading.Lock()


def set_log_context(uuid: int = None, stage: str = None, **kwargs):
    """Set the logging context for the current thread. Called by each stage at the start of its loop.
    
    Args:
        uuid: uuid of the persona currently being processed
        stage: name of the current stage (e.g. "stage4_events")
        **kwargs: extra key fields (event_id, event_idx, round, group_id, batch, 
                  call_type, app_type, category, member_name, image_path, etc.)
    """
    _log_context.uuid = uuid
    _log_context.stage = stage
    _log_context.extra = kwargs


def clear_log_context():
    """Clear the logging context for the current thread."""
    _log_context.uuid = None
    _log_context.stage = None
    _log_context.extra = {}


def update_log_context(**kwargs):
    """Update the extra fields in the current thread's logging context (does not affect uuid and stage)."""
    if not hasattr(_log_context, 'extra'):
        _log_context.extra = {}
    _log_context.extra.update(kwargs)


def _write_log_record(record: dict):
    """Write a single log record to the corresponding JSONL file."""
    if not LLM_CALL_LOGS_ENABLED:
        return
    
    uuid = record.get('uuid')
    stage = record.get('stage', 'unknown')
    
    if uuid is not None:
        log_dir = os.path.join(LLM_CALL_LOGS_DIR, f'uid{uuid}')
    else:
        log_dir = os.path.join(LLM_CALL_LOGS_DIR, '_global')
    
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f'{stage}.jsonl')
    
    with _log_write_lock:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def log_llm_call(model: str, input_text: str, output_text: str,
                 input_tokens: int = None, output_tokens: int = None):
    """Log a single text LLM call. Called internally by llm_request()."""
    if not LLM_CALL_LOGS_ENABLED:
        return
    
    uuid = getattr(_log_context, 'uuid', None)
    stage = getattr(_log_context, 'stage', None)
    extra = getattr(_log_context, 'extra', {}) or {}
    
    record = {
        'uuid': uuid,
        'stage': stage,
    }
    # Add the extra key fields
    for k, v in extra.items():
        if v is not None:
            record[k] = v
    
    record['model'] = model
    record['input'] = input_text
    record['output'] = output_text
    if input_tokens is not None:
        record['input_tokens'] = input_tokens
    if output_tokens is not None:
        record['output_tokens'] = output_tokens
    
    try:
        _write_log_record(record)
    except Exception as e:
        logger.warning(f"Failed to write LLM call log: {e}")


def log_image_api_call(model: str, prompt: str, output_path: str = None,
                       image_count: int = None):
    """Log a single image generation API call."""
    if not LLM_CALL_LOGS_ENABLED:
        return
    
    uuid = getattr(_log_context, 'uuid', None)
    stage = getattr(_log_context, 'stage', None)
    extra = getattr(_log_context, 'extra', {}) or {}
    
    record = {
        'uuid': uuid,
        'stage': stage,
    }
    for k, v in extra.items():
        if v is not None:
            record[k] = v
    
    record['model'] = model
    record['input'] = prompt
    record['output'] = output_path or ''
    if image_count is not None:
        record['image_count'] = image_count
    
    try:
        _write_log_record(record)
    except Exception as e:
        logger.warning(f"Failed to write image API call log: {e}")


# Lazily-created OpenAI clients so that importing this module never requires
# credentials or network configuration to be present. The text client targets the
# OpenAI-compatible chat API; the image client targets the image-generation API (DMX).
_client = None
_client_lock = threading.Lock()
_image_client = None
_image_client_lock = threading.Lock()


def get_client() -> OpenAI:
    """Return a process-wide OpenAI client for the text chat API, creating it on first use."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(
                    base_url=config.OPENAI_BASE_URL,
                    api_key=config.OPENAI_API_KEY,
                )
    return _client


def get_image_client() -> OpenAI:
    """Return a process-wide OpenAI client for the image-generation API (DMX), creating it on first use."""
    global _image_client
    if _image_client is None:
        with _image_client_lock:
            if _image_client is None:
                _image_client = OpenAI(
                    base_url=config.DMX_BASE_URL,
                    api_key=config.DMX_API_KEY,
                )
    return _image_client


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_random_exponential(min=config.WAIT_TIME_LOWER, max=config.WAIT_TIME_UPPER),
    stop=stop_after_attempt(config.RETRY_TIMES),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def llm_request(
    system_prompt: str, 
    user_prompt: str, 
    model: str = None,
    max_tokens: int = None,
    temperature: float = None,
    timeout: int = 300,
    return_parsed_json: bool = False,
    extract_json: bool = True,
    json_markers: Optional[List[str]] = None
) -> tuple:
    
    final_model = model or config.OPENAI_MODEL
    if not final_model:
        raise ValueError("Model name must be provided either as a parameter or in the OPENAI_MODEL environment variable.")

    if system_prompt != '':
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    else:
        messages = [
            {"role": "user", "content": user_prompt}
        ]

    # Build request parameters dynamically based on what's available
    request_params = {
        "model": final_model,
        "messages": messages
    }
    
    # Per-model max_tokens caps (API returns 400 if exceeded)
    _MODEL_MAX_TOKENS = {
        'deepseek-chat': 8192,
    }

    # Add optional parameters only if they exist in environment or are explicitly provided
    if max_tokens is not None:
        request_params["max_tokens"] = max_tokens
    elif os.getenv('OPENAI_MAX_TOKENS'):
        request_params["max_tokens"] = int(os.getenv('OPENAI_MAX_TOKENS'))

    # Cap max_tokens to model limit
    if "max_tokens" in request_params and final_model in _MODEL_MAX_TOKENS:
        request_params["max_tokens"] = min(request_params["max_tokens"], _MODEL_MAX_TOKENS[final_model])
    
    if temperature is not None:
        request_params["temperature"] = temperature
    elif os.getenv('OPENAI_TEMPERATURE'):
        request_params["temperature"] = float(os.getenv('OPENAI_TEMPERATURE'))
    
    if timeout is not None:
        request_params["timeout"] = timeout
    elif os.getenv('OPENAI_TIMEOUT'):
        request_params["timeout"] = int(os.getenv('OPENAI_TIMEOUT'))
        
    response = get_client().chat.completions.create(**request_params)

    content = response.choices[0].message.content.strip()

    cost_info = _calculate_cost(final_model, response.usage)

    # Log the LLM call
    input_text = f"[System]\n{system_prompt}\n\n[User]\n{user_prompt}" if system_prompt else user_prompt
    _input_tokens = cost_info.get('input_tokens')
    _output_tokens = cost_info.get('output_tokens')
    log_llm_call(final_model, input_text, content, _input_tokens, _output_tokens)

    if not extract_json:
        return content, cost_info


    parsed_json = _extract_json_from_content(content, json_markers)

    if return_parsed_json:
        return parsed_json, cost_info
    else:
        return content, cost_info
