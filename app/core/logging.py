import logging
import os
from logging.handlers import RotatingFileHandler
from app.core.config import settings

def setup_logging():
    log_dir = os.path.dirname(settings.LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(settings.LOG_FILE, maxBytes=10*1024*1024, backupCount=5),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("home_bot")

logger = setup_logging()
