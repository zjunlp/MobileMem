"""Image-generation capability (L1 backend) — DMX/doubao person & event images.

Generators import from here:
``from backends.images import generate_person_images, generate_event_images``.
Depends only on ``config`` + the text/image LLM client; never imports a generator
or the domain model.
"""
import requests
import base64
import time
from datetime import datetime
import os
import json
import config
from backends.llm import log_image_api_call

API_KEY = config.DMX_API_KEY  # DMXAPI API key
Generation_API_URL = config.DMX_GENERATION_URL  # DMXAPI image generation endpoint
Edit_API_URL = config.DMX_EDIT_URL  # DMXAPI image edit endpoint

QWEN_MAX = 500
GPT_MAX = 1000
DOUBAO_MAX = 1000
CHINESE_GENERATION_MODEL = config.DMX_CHINESE_GENERATION_MODEL
CHINESE_EDIT_MODEL = config.DMX_CHINESE_EDIT_MODEL
CHINESE_EDIT_FALLBACK_MODELS = [
    "doubao-seedream-5-0-260128",
    "doubao-seededit-3-0-i2i-250628",
    "qwen-image-edit",
]


# OpenRouter image backend (Gemini "nano-banana"), routed through local proxy
# Active when config.IMAGE_PROVIDER == "openrouter" (the default). OpenRouter is
# reachable only through the local proxy, which drops oversized TLS upload
# bodies, so input images are downscaled before sending and transient SSL
# errors are retried. The legacy DMX code paths below are used when
# IMAGE_PROVIDER == "dmx".
import io  # noqa: E402
from PIL import Image  # noqa: E402

_IMAGE_SESSION = None


def _image_session():
    """A requests session with trust_env=False so a process-wide NO_PROXY
    cannot override the explicit proxy we need to reach OpenRouter."""
    global _IMAGE_SESSION
    if _IMAGE_SESSION is None:
        s = requests.Session()
        s.trust_env = False
        _IMAGE_SESSION = s
    return _IMAGE_SESSION


def _image_proxies():
    if not config.IMAGE_HTTP_PROXY:
        return None
    return {"http": config.IMAGE_HTTP_PROXY, "https": config.IMAGE_HTTP_PROXY}


def _image_to_data_uri(path, max_side=None):
    """Load a local image, downscale it, and return a compact JPEG data URI."""
    max_side = max_side or config.IMAGE_MAX_INPUT_SIDE
    im = Image.open(path).convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / float(max(w, h)))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _openrouter_image_call(prompt, input_image_paths=None, model=None, timeout=180):
    """Call OpenRouter's image model and return a list of raw image bytes.

    With input_image_paths it performs an image edit (inputs attached as
    downscaled data URIs); otherwise it is plain text-to-image. Transient
    SSL/connection errors (the proxy occasionally drops TLS) are retried.
    """
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set; refusing to call OpenRouter "
            "(set it explicitly — cross-provider key fallback was removed "
            "to prevent credential leakage)"
        )
    model = model or config.OPENROUTER_IMAGE_MODEL
    url = config.OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    if input_image_paths:
        content = [{"type": "text", "text": prompt}]
        for p in input_image_paths:
            try:
                content.append({"type": "image_url", "image_url": {"url": _image_to_data_uri(p)}})
            except FileNotFoundError:
                print(f"[WARN] input image not found: {p}")
            except Exception as e:
                print(f"[WARN] failed to load input image {p}: {e}")
    else:
        content = prompt

    payload = {
        "model": model,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": content}],
    }
    proxies = _image_proxies()
    sess = _image_session()

    last_err = None
    for attempt in range(config.IMAGE_RETRY_TIMES):
        try:
            r = sess.post(url, json=payload, headers=headers, proxies=proxies, timeout=timeout)
            if r.status_code == 200:
                msg = r.json()["choices"][0]["message"]
                out = []
                for item in (msg.get("images") or []):
                    u = (item.get("image_url") or {}).get("url", "")
                    if u.startswith("data:"):
                        out.append(base64.b64decode(u.split(",", 1)[1]))
                    elif u:
                        ir = sess.get(u, proxies=proxies, timeout=60)
                        ir.raise_for_status()
                        out.append(ir.content)
                if out:
                    return out
                last_err = "HTTP 200 but no image in response"
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                # Auth/credit/not-found errors will not recover by retrying.
                if r.status_code in (401, 402, 403, 404):
                    print(f"[FAIL] OpenRouter image: {last_err}")
                    break
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
        # Transient network errors: back off and retry.
        time.sleep(min(2 + attempt * 2, 15))

    print(f"[FAIL] OpenRouter image after {config.IMAGE_RETRY_TIMES} attempts: {last_err}")
    return []


def _save_image_bytes(images, output_dir, prefix):
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    multi = len(images) > 1
    for i, raw in enumerate(images):
        suffix = f"_{i + 1}" if multi else ""
        fp = os.path.join(output_dir, f"{prefix}_{ts}{suffix}.png")
        with open(fp, "wb") as f:
            f.write(raw)
        paths.append(fp)
        print(f"[OK] image saved: {fp} ({os.path.getsize(fp) / 1024:.1f} KB)")
    return paths


def get_generation_model_and_limit(nationality):
    # Model comes from config (DMX_CHINESE_GENERATION_MODEL); previously the
    # doubao model name was hardcoded here, which blocked pointing the DMX
    # path at other OpenAI-compatible image gateways (e.g. gpt-image-2).
    model = CHINESE_GENERATION_MODEL
    limit = DOUBAO_MAX if model.startswith("doubao-seed") else GPT_MAX
    return model, limit


def get_edit_model_candidates(nationality):
    candidates = [CHINESE_EDIT_MODEL]
    for m in CHINESE_EDIT_FALLBACK_MODELS:
        if m != CHINESE_EDIT_MODEL and m not in candidates:
            candidates.append(m)
    return candidates


def get_edit_prompt_limit(model_name):
    if model_name == "qwen-image-edit":
        return QWEN_MAX
    if model_name.startswith("doubao-seed"):
        return DOUBAO_MAX
    return GPT_MAX


def build_edit_headers(model_name):
    if model_name == "qwen-image-edit":
        return {"Authorization": f"{API_KEY}"}
    if model_name.startswith("doubao-seed"):
        return {"Authorization": f"{API_KEY}"}
    return {"Authorization": f"Bearer {API_KEY}"}


def build_generation_headers(model_name):
    if model_name.startswith("doubao-seedream"):
        return {"Authorization": f"{API_KEY}", "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def get_default_image_size(model_name):
    if model_name.startswith("doubao-seed"):
        return "2K"
    return "1024x1024"


def generate_person_images(prompt, output_dir="output", nationality="Chinese"):
    if config.IMAGE_PROVIDER == "openrouter":
        images = _openrouter_image_call(prompt)
        paths = _save_image_bytes(images, output_dir, "generated_image")
        log_image_api_call(model=config.OPENROUTER_IMAGE_MODEL, prompt=prompt,
                           output_path=paths[0] if paths else "", image_count=len(paths))
        return paths

    filepath_lst = []

    # Truncate the prompt to avoid API length errors
    model_name, max_len = get_generation_model_and_limit(nationality)

    if len(prompt) > max_len:
        original_len = len(prompt)
        prompt = prompt[:max_len]
        print(f"[WARN] prompt truncated: {original_len} -> {len(prompt)} chars")

    payload = {
        "prompt": prompt,
        "n": 1,
        "model": model_name,
        "size": get_default_image_size(model_name),
    }

    headers = build_generation_headers(model_name)

    try:
        print("=" * 50)
        print("[*] Generating image...")
        print(f"   Nationality: {nationality}")
        print(f"   Model: {payload['model']}")
        print("=" * 50)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"[OK] Created output dir: {output_dir}")
        else:
            print(f"[OK] Output dir exists: {output_dir}")

        print("[..] Sending API request...")
        print(f"   Model: {payload['model']}")
        print(f"   Size: {payload['size']}")
        print(f"   Count: {payload['n']}")
        print(f"   Prompt length: {len(payload['prompt'])} chars")

        response = requests.post(Generation_API_URL, json=payload, headers=headers, timeout=180)
        response.raise_for_status()  # Check the HTTP status code and raise on error

        result = response.json()
        print("[OK] API response received")
        if 'data' in result and len(result['data']) > 0:
            print("[..] Saving images...")

            # Iterate over each returned image
            # In practice only one image is returned; this loop is a defensive strategy
            for i, image_data in enumerate(result['data']):
                # Handle base64-encoded images (gpt-image-1 return format)
                if 'b64_json' in image_data:
                    # Decode the base64 data
                    base64_data = image_data['b64_json']
                    image_bytes = base64.b64decode(base64_data)

                    # Generate a unique filename (timestamp + index)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"generated_image_{timestamp}_{i + 1}.png"
                    filepath = os.path.join(output_dir, filename)

                    # Save the image locally; only record the path once the
                    # file actually exists on disk
                    with open(filepath, 'wb') as f:
                        f.write(image_bytes)
                    filepath_lst.append(filepath)

                    # Get the file size
                    file_size = os.path.getsize(filepath) / 1024  # convert to KB
                    print(f"   [OK] Image {i + 1}: {filepath} ({file_size:.2f} KB)")

                # Handle URL-format images (dall-e-3 return format)
                elif 'url' in image_data:
                    print(f"   [OK] Image {i + 1} URL: {image_data['url']}")
                    print("   [WARN] URL expires in 60 minutes, download promptly")

                    # Download the URL image and save it
                    try:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"generated_image_{timestamp}_{i + 1}_url.png"
                        filepath = os.path.join(output_dir, filename)

                        # Download the image; only record the path once the
                        # file actually exists on disk
                        img_resp = requests.get(image_data['url'], timeout=60)
                        img_resp.raise_for_status()
                        with open(filepath, 'wb') as f:
                            f.write(img_resp.content)
                        filepath_lst.append(filepath)

                        # Get the file size
                        file_size = os.path.getsize(filepath) / 1024  # convert to KB
                        print(f"   [OK] Image {i + 1} downloaded: {filepath} ({file_size:.2f} KB)")
                    except Exception as e:
                        print(f"   [FAIL] Download failed: {e}")

            print(f"{'=' * 50}")
            print("[DONE] All images processed")
            print(f"{'=' * 50}")
        else:
            print("[FAIL] No image data found, check API response")

    except requests.exceptions.RequestException as e:
        # Network request error handling
        print(f"{'=' * 50}")
        print("[FAIL] Request error!")
        print(f"{'=' * 50}")
        print(f"Error: {e}")

        # Print the detailed error response. `is not None`, not truthiness:
        # a 4xx/5xx Response is falsy, which used to hide the error body.
        if e.response is not None:
            print(f"HTTP status: {e.response.status_code}")
            print(f"Response: {e.response.text}")

    except Exception as e:
        print(f"{'=' * 50}")
        print("[FAIL] Unknown error!")
        print(f"{'=' * 50}")
        print(f"Error: {e}")

    # Log the image generation API call
    log_image_api_call(
        model=payload.get('model', 'unknown'),
        prompt=prompt,
        output_path=filepath_lst[0] if filepath_lst else '',
        image_count=len(filepath_lst),
    )

    return filepath_lst
    # Returns the list of image paths


def generate_event_images(prompt, image_paths, output_dir="output", nationality="Chinese"):
    if config.IMAGE_PROVIDER == "openrouter":
        images = _openrouter_image_call(prompt, input_image_paths=image_paths)
        paths = _save_image_bytes(images, output_dir, "edited")
        log_image_api_call(model=config.OPENROUTER_IMAGE_MODEL, prompt=prompt,
                           output_path=paths[0] if paths else "", image_count=len(paths))
        return paths

    filepath_lst = []
    # Defined up front so the final log call is safe even when no input file
    # could be loaded (previously a NameError on the empty-`files` path).
    payload = {}

    # Truncate the prompt to avoid API length errors (qwen-image-edit has a stricter limit)
    model_candidates = get_edit_model_candidates(nationality)


    files = []

    # Iterate over the configured image paths and prepare the upload files
    for img_path in image_paths:
        try:
            # basename, not split('/'): Windows paths use '\' and would leak
            # the full absolute path as the multipart filename.
            file_name = os.path.basename(img_path)

            # Infer the MIME type automatically from the file extension
            mime_type = "image/png" if img_path.lower().endswith(".png") else "image/jpeg"

            # Add the file to the upload list
            # Format: (param_name, (filename, file_object, MIME_type))
            files.append(
                ("image",  # the fixed parameter name required by the API
                 (file_name,  # original filename
                  open(img_path, "rb"),  # open the file in binary read-only mode
                  mime_type)  # the file's MIME type
                 )
            )

        except FileNotFoundError:
            print(f"[WARN] File not found - {img_path}")

        except Exception as e:
            print(f"[WARN] Error processing file - {img_path}: {str(e)}")


    # try/finally so upload handles are closed even when requests.post raises
    # or the moderation check raises RuntimeError mid-loop.
    try:
        if not files:
            # If no image file was successfully loaded
            print("[FAIL] No image files available")

        else:
            for model_name in model_candidates:
                candidate_prompt = prompt
                candidate_limit = get_edit_prompt_limit(model_name)
                if len(candidate_prompt) > candidate_limit:
                    original_len = len(candidate_prompt)
                    candidate_prompt = candidate_prompt[:candidate_limit]
                    print(f"[WARN] prompt truncated: {original_len} -> {len(candidate_prompt)} chars")

                payload = {
                    "model": model_name,
                    "prompt": candidate_prompt,
                    "size": get_default_image_size(model_name),
                }
                if not model_name.startswith("doubao-seed"):
                    payload["background"] = "auto"
                    payload["output_compression"] = 100
                    payload["output_format"] = "png"
                    payload["quality"] = "high"
                headers = build_edit_headers(model_name)

                # Same-model retry: for transient errors (e.g. 451/500/502/503/504), retry the same model first, then consider fallback
                SAME_MODEL_RETRIES = 3
                RETRY_DELAY = 5
                response = None
                for retry_idx in range(SAME_MODEL_RETRIES):
                    for _, file_tuple in files:
                        file_tuple[1].seek(0)

                    print("=" * 50)
                    print(f"[*] Generating event image... (attempt {retry_idx+1}/{SAME_MODEL_RETRIES})")
                    print(f"   Nationality: {nationality}")
                    print(f"   Model: {payload['model']}")
                    print("=" * 50)

                    response = requests.post(
                        Edit_API_URL,
                        headers=headers,
                        data=payload,
                        files=files,
                        timeout=180
                    )

                    if response.status_code == 200:
                        break

                    print(f"[FAIL] Request error: HTTP {response.status_code}")
                    print(f"Response: {response.text}")
                    # Content moderation blocks are not retried; raise immediately
                    try:
                        err_code = response.json().get("error", {}).get("code", "")
                    except Exception:
                        err_code = ""
                    if err_code == "moderation_blocked" or "safety system" in response.text:
                        raise RuntimeError(f"moderation_blocked: {response.text[:200]}")
                    # Retry the same model on transient errors
                    if retry_idx < SAME_MODEL_RETRIES - 1:
                        print(f"[->] Retrying same model ({model_name}) in {RETRY_DELAY}s...")
                        time.sleep(RETRY_DELAY)

                if response.status_code != 200:
                    if model_name != model_candidates[-1]:
                        print(f"[->] Fallback to next edit model: {model_candidates[model_candidates.index(model_name) + 1]}")
                        continue
                    break

                try:
                    data = response.json()
                    os.makedirs(output_dir, exist_ok=True)

                    if data.get("data") and isinstance(data["data"], list):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        for idx, item in enumerate(data["data"]):
                            image_b64 = item.get("b64_json")
                            image_url = item.get("url")

                            if image_b64:
                                filename = f"edited_{timestamp}_{idx + 1}.png" if len(data["data"]) > 1 else f"edited_{timestamp}.png"
                                output_path = os.path.join(output_dir, filename)
                                with open(output_path, "wb") as f:
                                    f.write(base64.b64decode(image_b64))
                                # Only record the path once the file actually exists on disk
                                filepath_lst.append(output_path)
                                print(f"[OK] Image saved (base64): {output_path}")
                            elif image_url:
                                filename = f"edited_{timestamp}_{idx + 1}.png" if len(data["data"]) > 1 else f"edited_{timestamp}.png"
                                output_path = os.path.join(output_dir, filename)
                                try:
                                    img_resp = requests.get(image_url, timeout=60)
                                    img_resp.raise_for_status()
                                    with open(output_path, "wb") as f:
                                        f.write(img_resp.content)
                                    # Only record the path once the file actually exists on disk
                                    filepath_lst.append(output_path)
                                    print(f"[OK] Image saved (URL): {output_path}")
                                except Exception as e:
                                    print(f"[FAIL] Download failed: {e}")
                            else:
                                print(f"[WARN] No image data for item {idx + 1} (no b64_json or url)")
                        break

                    print("[FAIL] Unexpected response structure")
                    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    if model_name != model_candidates[-1]:
                        print(f"[->] Fallback to next edit model: {model_candidates[model_candidates.index(model_name) + 1]}")
                        continue
                except json.JSONDecodeError:
                    print("[FAIL] JSON parse error")
                    print(f"Response: {response.text}")
                    if model_name != model_candidates[-1]:
                        print(f"[->] Fallback to next edit model: {model_candidates[model_candidates.index(model_name) + 1]}")
                        continue
                break
    finally:
        for _, file_tuple in files:
            try:
                file_tuple[1].close()
            except Exception:
                # Best-effort close of upload handles; a leaked handle is freed
                # at process exit and must not mask the real result.
                pass

    # Log the image edit API call
    log_image_api_call(
        model=payload.get('model', 'unknown'),
        prompt=prompt,
        output_path=filepath_lst[0] if filepath_lst else '',
        image_count=len(filepath_lst),
    )

    return filepath_lst
