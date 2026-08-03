"""Standard logger factory: console handler plus optional file handler under LOG_DIR."""

import logging
import os

from config import LOG_DIR


def setup_logger(name, log_file=None, level=logging.INFO):
    """Create a standard logger."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        if log_file:
            fh = logging.FileHandler(os.path.join(LOG_DIR, log_file), encoding='utf-8')
            fh.setFormatter(fmt)
            logger.addHandler(fh)
    return logger
