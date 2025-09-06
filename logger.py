import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "operations.log")

logger = logging.getLogger("good_news")
logger.setLevel(logging.INFO)

# Only add handlers if they don't already exist
if not logger.handlers:
    # File handler with module info
    file_handler = logging.FileHandler("operations.log")
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler with module info
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        '[%(levelname)s] %(module)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)