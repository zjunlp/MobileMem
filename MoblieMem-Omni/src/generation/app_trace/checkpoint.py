"""App-trace render checkpoint (resume) persistence."""
import json
import logging
import os

logger = logging.getLogger('fix_app_screenshots')


def _ckpt_path(output_dir):
    return os.path.join(output_dir, '.app_screenshot_checkpoint.json')

def load_checkpoint(output_dir):
    path = _ckpt_path(output_dir)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return set(data.get('done', []))
        except Exception:
            pass
    return set()

def save_checkpoint(output_dir, done_set):
    path = _ckpt_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'done': sorted(done_set)}, f, ensure_ascii=False, indent=2)

def clear_checkpoint(output_dir):
    path = _ckpt_path(output_dir)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f'Checkpoint cleared: {path}')
