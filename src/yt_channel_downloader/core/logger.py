import logging
from typing import Callable, Optional


_BASE_LOGGER_NAME = "yt_channel_downloader"
_logger_factory: Optional[Callable[[str], logging.Logger]] = None
_android_logcat_handler: Optional[logging.Handler] = None


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


class AndroidLogcatHandler(logging.Handler):
    """Forward Python log records to Android's Logcat when running under Chaquopy."""

    _MAX_TAG_LENGTH = 23
    _MAX_MESSAGE_LENGTH = 4000

    def __init__(self) -> None:
        super().__init__()
        self._log_class = self._resolve_log_class()

    @staticmethod
    def _resolve_log_class():
        try:
            from java import jclass  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        try:
            return jclass("android.util.Log")
        except Exception:  # noqa: BLE001
            return None

    def available(self) -> bool:
        return self._log_class is not None

    def emit(self, record: logging.LogRecord) -> None:
        if self._log_class is None:
            return

        try:
            message = self.format(record)
            priority = self._priority_for_level(record.levelno)
            tag = self._tag_for_record(record.name)
            for chunk in self._split_message(message):
                self._log_class.println(priority, tag, chunk)
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def _priority_for_level(self, levelno: int) -> int:
        if levelno >= logging.ERROR:
            return int(getattr(self._log_class, "ERROR", 6))
        if levelno >= logging.WARNING:
            return int(getattr(self._log_class, "WARN", 5))
        if levelno >= logging.INFO:
            return int(getattr(self._log_class, "INFO", 4))
        return int(getattr(self._log_class, "DEBUG", 3))

    def _tag_for_record(self, logger_name: str) -> str:
        suffix = logger_name
        if logger_name.startswith(f"{_BASE_LOGGER_NAME}."):
            suffix = logger_name.split(".")[-1]
        elif logger_name == _BASE_LOGGER_NAME:
            suffix = "core"
        else:
            suffix = logger_name.split(".")[-1]

        tag = f"YTCD-{suffix}"
        if len(tag) <= self._MAX_TAG_LENGTH:
            return tag
        return tag[:self._MAX_TAG_LENGTH]

    def _split_message(self, message: str):
        if not message:
            yield ""
            return
        for start in range(0, len(message), self._MAX_MESSAGE_LENGTH):
            yield message[start:start + self._MAX_MESSAGE_LENGTH]


def configure_android_logging(level: int = logging.INFO) -> bool:
    """
    Attach an Android Logcat handler when running inside the Android app.

    Returns:
        bool: True if Android logging is active, otherwise False.
    """
    global _android_logcat_handler

    if _android_logcat_handler is None:
        handler = AndroidLogcatHandler()
        if not handler.available():
            return False
        handler.setFormatter(logging.Formatter("%(message)s"))
        _android_logcat_handler = handler

    configure_logging(level=level, handler=_android_logcat_handler)
    return True


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
