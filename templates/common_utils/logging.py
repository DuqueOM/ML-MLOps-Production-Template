"""Structured logging for ML services.

Supports two formats controlled by LOG_FORMAT environment variable:
- "json"  → Structured JSON (production, K8s log aggregation)
- "human" → Colored human-readable (local development)

Log level controlled by LOG_LEVEL env var (default: INFO).
Service name injected via SERVICE_NAME env var.

Usage:
    from common_utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Training started", extra={"epoch": 1, "lr": 0.001})

    # In production (LOG_FORMAT=json):
    # {"timestamp": "2024-01-15T10:30:00", "level": "INFO", "service": "bankchurn",
    #  "module": "train", "message": "Training started", "epoch": 1, "lr": 0.001}

    # In development (LOG_FORMAT=human):
    # 2024-01-15 10:30:00 INFO [train] Training started

TODO: Set SERVICE_NAME env var in your Dockerfile or K8s deployment.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter for production environments.

    Outputs one JSON object per line — compatible with:
    - Kubernetes log aggregation (Fluentd, Fluent Bit)
    - Google Cloud Logging
    - AWS CloudWatch
    - ELK stack
    """

    def __init__(self, service_name: str = "ml-service") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Include extra fields (e.g., epoch, lr, metrics)
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in {
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                    "taskName",
                }:
                    log_entry[key] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable colored formatter for local development."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{timestamp} {color}{record.levelname:8s}{self.RESET} " f"[{record.module}] {record.getMessage()}"


def get_logger(
    name: str,
    level: str | None = None,
    log_format: str | None = None,
) -> logging.Logger:
    """Get a configured logger instance.

    Parameters
    ----------
    name : str
        Logger name (typically __name__).
    level : str, optional
        Log level override. Defaults to LOG_LEVEL env var or "INFO".
    log_format : str, optional
        Format override. Defaults to LOG_FORMAT env var or "human".

    Returns
    -------
    logging.Logger
        Configured logger with appropriate formatter.
    """
    logger = logging.getLogger(name)

    # Only configure if no handlers exist (avoid duplicate handlers)
    if not logger.handlers:
        level = level or os.environ.get("LOG_LEVEL", "INFO")
        log_format = log_format or os.environ.get("LOG_FORMAT", "human")
        service_name = os.environ.get("SERVICE_NAME", "ml-service")

        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        handler = logging.StreamHandler(sys.stdout)

        if log_format.lower() == "json":
            handler.setFormatter(JSONFormatter(service_name))
        else:
            handler.setFormatter(HumanFormatter())

        logger.addHandler(handler)
        logger.propagate = False

    return logger
