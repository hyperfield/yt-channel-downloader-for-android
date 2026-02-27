from typing import Any, MutableMapping


# Default download-count thresholds for when to re-prompt.
DEFAULT_SUPPORT_PROMPT_SHORT_SNOOZE = 25
DEFAULT_SUPPORT_PROMPT_MEDIUM_SNOOZE = 50
DEFAULT_SUPPORT_PROMPT_LONG_SNOOZE = 100
DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD = DEFAULT_SUPPORT_PROMPT_SHORT_SNOOZE

SUPPORT_PROMPT_CHOICE_SUPPORT = "support"
SUPPORT_PROMPT_CHOICE_NOT_SURE = "not_sure"
SUPPORT_PROMPT_CHOICE_CANNOT_DONATE = "cannot_donate"


class SupportPrompt:
    """
    Qt-free helper for support prompt milestone logic.

    It stores state in a mutable settings mapping with these keys:
    - downloads_completed
    - support_prompt_next_at
    - support_prompt_last_shown_at
    """

    def __init__(
        self,
        short_snooze: int = DEFAULT_SUPPORT_PROMPT_SHORT_SNOOZE,
        medium_snooze: int = DEFAULT_SUPPORT_PROMPT_MEDIUM_SNOOZE,
        long_snooze: int = DEFAULT_SUPPORT_PROMPT_LONG_SNOOZE,
    ) -> None:
        self.default_short_snooze = self._safe_positive_int(
            short_snooze,
            DEFAULT_SUPPORT_PROMPT_SHORT_SNOOZE,
        )
        self.default_medium_snooze = self._safe_positive_int(
            medium_snooze,
            DEFAULT_SUPPORT_PROMPT_MEDIUM_SNOOZE,
        )
        self.default_long_snooze = self._safe_positive_int(
            long_snooze,
            DEFAULT_SUPPORT_PROMPT_LONG_SNOOZE,
        )

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_positive_int(self, value: Any, default: int) -> int:
        return max(1, self._safe_int(value, default))

    @property
    def min_gap(self) -> int:
        return self.default_short_snooze

    def normalize_state(self, settings: MutableMapping[str, Any]) -> tuple[int, int, int]:
        """
        Normalize support prompt counters in-place and return:
        (downloads_completed, support_prompt_next_at, support_prompt_last_shown_at)
        """
        completed = self._safe_int(settings.get("downloads_completed", 0), 0)
        if completed < 0:
            completed = 0

        last_shown_at = self._safe_int(settings.get("support_prompt_last_shown_at", 0), 0)
        if last_shown_at < 0:
            last_shown_at = 0

        next_at = self._safe_int(
            settings.get("support_prompt_next_at", DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD),
            DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD,
        )
        if next_at <= last_shown_at:
            next_at = last_shown_at + self.min_gap

        settings["downloads_completed"] = completed
        settings["support_prompt_last_shown_at"] = last_shown_at
        settings["support_prompt_next_at"] = next_at
        return completed, next_at, last_shown_at

    def should_prompt(self, completed: int, next_at: int, last_shown_at: int = 0) -> bool:
        """Return True when the support prompt should be shown."""
        return completed >= next_at and (completed - last_shown_at) >= self.min_gap

    def should_prompt_for_settings(self, settings: MutableMapping[str, Any]) -> bool:
        completed, next_at, last_shown_at = self.normalize_state(settings)
        return self.should_prompt(completed, next_at, last_shown_at)

    def register_download_complete(self, settings: MutableMapping[str, Any], count: int = 1) -> int:
        """
        Increment completed downloads by `count` and normalize state.

        Returns the updated downloads_completed value.
        """
        delta = self._safe_int(count, 1)
        if delta < 1:
            delta = 1
        settings["downloads_completed"] = self._safe_int(settings.get("downloads_completed", 0), 0) + delta
        completed, _, _ = self.normalize_state(settings)
        return completed

    def _choice_to_snooze(self, choice: str) -> int:
        normalized = (choice or "").strip().lower()
        if normalized in (SUPPORT_PROMPT_CHOICE_SUPPORT, "support"):
            return self.default_long_snooze
        if normalized in (
            SUPPORT_PROMPT_CHOICE_CANNOT_DONATE,
            "cannot_donate",
            "i cannot donate",
        ):
            return self.default_medium_snooze
        return self.default_short_snooze

    def next_threshold_for_choice(self, completed: int, choice: str) -> int:
        snooze = self._choice_to_snooze(choice)
        return completed + snooze

    def register_prompt_result(self, settings: MutableMapping[str, Any], choice: str) -> int:
        """
        Apply the user's prompt choice and return the new support_prompt_next_at.

        This method is defensive: if state is stale/invalid, it enforces a minimum
        gap to avoid prompting again after a single download.
        """
        completed, _, _ = self.normalize_state(settings)
        new_threshold = self.next_threshold_for_choice(completed, choice)
        if new_threshold <= completed:
            new_threshold = completed + self.min_gap
        settings["support_prompt_next_at"] = new_threshold
        settings["support_prompt_last_shown_at"] = completed
        return new_threshold
