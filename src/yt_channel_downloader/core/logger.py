import logging
from typing import Callable, Optional


_BASE_LOGGER_NAME = "yt_channel_downloader"
_logger_factory: Optional[Callable[[str], logging.Logger]] = None


def set_logger_factory(factory: Optional[Callable[[str], logging.Logger]]) -> None:
    """Set a logger factory so host apps can control logger instances."""
    global _logger_factory
    _logger_factory = factory


def configure_logging(
    level: int = logging.INFO,
    handler: Optional[logging.Handler] = None,
) -> logging.Logger:
    """
    Configure the base logger with an optional handler.

    By default, this does not attach any handlers so host apps can provide
    their own (e.g., Android Logcat handlers).
    """
    logger = logging.getLogger(_BASE_LOGGER_NAME)
    logger.setLevel(level)
    if handler is not None and handler not in logger.handlers:
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Return a logger scoped under the application namespace.

    Args:
        name (Optional[str]): Optional suffix for the logger (e.g. module name).

    Returns:
        logging.Logger: Logger instance.
    """
    logger_name = _BASE_LOGGER_NAME if not name else f"{_BASE_LOGGER_NAME}.{name}"
    if _logger_factory:
        return _logger_factory(logger_name)
    return logging.getLogger(logger_name)
