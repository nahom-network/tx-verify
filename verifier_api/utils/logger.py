"""Logging configuration mirroring the Winston logger from the TypeScript codebase."""

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class EmojiFormatter(logging.Formatter):
    """Console formatter with emoji prefixes matching the TS emoji format."""

    EMOJIS = {
        "INFO": "\u2139\ufe0f ",
        "WARNING": "\u26a0\ufe0f ",
        "ERROR": "\u274c",
        "DEBUG": "\U0001f41b",
    }

    def format(self, record: logging.LogRecord) -> str:
        emoji = self.EMOJIS.get(record.levelname, "")
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        msg = f"{emoji}[{timestamp}] {record.levelname}: {record.getMessage()}"
        if record.exc_info and record.exc_info[1]:
            msg += f"\n\U0001f50d Stack:\n{self.formatException(record.exc_info)}"
        return msg


class FileFormatter(logging.Formatter):
    """Plain file formatter matching the TS file format."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        msg = f"[{timestamp}] {record.levelname}: {record.getMessage()}"
        if record.exc_info and record.exc_info[1]:
            msg += f"\n{self.formatException(record.exc_info)}"
        return msg


def _setup_logger() -> logging.Logger:
    """Create and configure the application logger."""
    log = logging.getLogger("verifier-api")

    env = os.getenv("NODE_ENV", os.getenv("ENV", "development"))
    level_name = os.getenv("LOG_LEVEL", "INFO" if env == "production" else "DEBUG")
    log.setLevel(getattr(logging, level_name.upper(), logging.DEBUG))

    # Prevent duplicate handlers on re-import
    if log.handlers:
        return log

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(EmojiFormatter())
    log.addHandler(console)

    # File handlers (rotating daily, 14-day retention)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    error_handler = TimedRotatingFileHandler(log_dir / "error.log", when="midnight", backupCount=14)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(FileFormatter())
    log.addHandler(error_handler)

    combined_handler = TimedRotatingFileHandler(
        log_dir / "combined.log", when="midnight", backupCount=14
    )
    combined_handler.setFormatter(FileFormatter())
    log.addHandler(combined_handler)

    return log


logger = _setup_logger()
