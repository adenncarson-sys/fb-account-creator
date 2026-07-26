#!/usr/bin/env python3
"""
Logging utility – real-time console output with colors + file logging.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to console output."""

    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(name: str = "FBCreator") -> logging.Logger:
    """Create and return a configured logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Console handler (colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = ColoredFormatter("[%(asctime)s] %(levelname)-8s %(message)s",
                                   datefmt="%H:%M:%S")
    console_handler.setFormatter(console_fmt)

    # File handler (plain)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(LOG_DIR / f"fb_creator_{timestamp}.log",
                                       encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s",
                                 datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_fmt)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


# Singleton logger used across modules
log = setup_logger()
