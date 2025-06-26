import logging.config
import os
import requests

LOGS_DIR = "logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

TEN_MB = 10 * 1024 * 1024

DISCORD_WEBHOOK_URL = None
DISCORD_MAX_MESSAGE_LENGTH = 2000  # Discord's max message length


class DiscordWebhookHandler(logging.Handler):
    """
    Custom logging handler to send logs to a Discord webhook.
    Batch messages until they reach the maximum length.
    """

    def __init__(self):
        super().__init__()
        self.buffer = ""
        self.last_message_time = None

    def emit(self, record):
        log_entry = self.format(record)
        webhook_url = DISCORD_WEBHOOK_URL
        if log_entry.endswith("[racetime_bot] - INFO - Refresh races"):
            # Skip this specific log entry so we don't spam Discord
            return
        if webhook_url:
            if (
                len(self.buffer) + len(log_entry) + len("\n")
                >= DISCORD_MAX_MESSAGE_LENGTH
            ) or (
                self.last_message_time and (record.created - self.last_message_time) > 5
            ):
                # If the buffer is full, send the current buffer and reset it
                requests.post(webhook_url, json={"content": self.buffer})
                self.buffer = ""
            self.buffer += log_entry + "\n"
            self.last_message_time = record.created
    
    def close(self):
        """
        Flush any remaining logs in the buffer when the handler is closed.
        """
        if self.buffer:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": self.buffer})
            self.buffer = ""
        super().close()


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,  # Don't disable existing loggers like Alembic
    "formatters": {
        "standard": {
            # - Timestamp (asctime)
            # - Logger Name (name): This is your component identifier (e.g., 'fastapi_app', 'discord_bot')
            # - Log Level (levelname)
            # - The actual log message (message)
            "format": "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "discord_webhook": {
            "level": "DEBUG",
            "class": DiscordWebhookHandler,
            "formatter": "standard",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file_app": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": os.path.join(LOGS_DIR, "application.log"),
            "maxBytes": TEN_MB,
            "backupCount": 5,
            "encoding": "utf-8",
        },
        "file_error": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": os.path.join(LOGS_DIR, "error.log"),
            "maxBytes": TEN_MB,
            "backupCount": 2,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        # Catch-all, default logger
        "": {
            "handlers": ["console", "file_app", "file_error", "discord_webhook"],
            "level": "DEBUG",
            "propagate": True,
        },
        # Per component loggers
        "pyladderchicken": {
            "handlers": ["console", "file_app", "discord_webhook"],
            "level": "DEBUG",
            "propagate": False,
        },
        "fastapi": {
            "handlers": ["console", "file_app", "discord_webhook"],
            "level": "DEBUG",
            "propagate": False,
        },
        "discord": {
            "handlers": ["console", "file_app", "discord_webhook"],
            "level": "DEBUG",
            "propagate": False,
        },
        "racetime": {
            "handlers": ["console", "file_app", "discord_webhook"],
            "level": "DEBUG",
            "propagate": False,
        },
        "avianart": {
            "handlers": ["console", "file_app", "discord_webhook"],
            "level": "DEBUG",
            "propagate": False,
        },
        "twitch": {
            "handlers": ["console", "file_app", "discord_webhook"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Alembic
        "alembic": {
            "handlers": ["console", "discord_webhook"],
            "level": "INFO",
            "propagate": False,  # Don't go to root
        },
    },
    "root": {  # Tehcnically redundant
        "handlers": ["console", "file_app", "file_error", "discord_webhook"],
        "level": "INFO",
    },
}


def setup_logging(config: dict):
    """Configures the logging system for the application."""
    global DISCORD_WEBHOOK_URL
    DISCORD_WEBHOOK_URL = config.get("discord_logging_webhook_url", None)

    if not DISCORD_WEBHOOK_URL:
        del LOGGING_CONFIG["handlers"]["discord_webhook"]
        for logger in LOGGING_CONFIG["loggers"].values():
            if "discord_webhook" in logger["handlers"]:
                logger["handlers"].remove("discord_webhook")
        if "discord_webhook" in LOGGING_CONFIG["root"]["handlers"]:
            LOGGING_CONFIG["root"]["handlers"].remove("discord_webhook")

    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger("logging_setup")  # Will get root logger
    logger.info("Logging configured successfully!")
