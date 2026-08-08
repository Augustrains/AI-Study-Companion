from __future__ import annotations

from typing import Any

from domain.learner_profile import LearnerProfile, LearningPreferences


class LearnerProfileService:
    """Validate and normalize profile fields without performing persistence."""

    VALID_LEVELS = {"unknown", "none", "basic", "practice", "independent"}
    VALID_CONTENT_STYLES = {"balanced", "concise", "detailed", "example_first"}
    VALID_DIFFICULTIES = {"adaptive", "easy", "challenging"}
    VALID_FREQUENCIES = {"flexible", "daily", "frequent", "occasional"}
    VALID_DURATIONS = {15, 30, 45, 60}

    def build_profile(self, payload: dict[str, Any]) -> LearnerProfile:
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")

        user_id = self._required_text(payload, "user_id")
        learning_domain = self._required_text(payload, "learning_domain")
        background = self._required_text(payload, "background")
        level = self._enum(payload.get("self_assessed_level", "unknown"), self.VALID_LEVELS, "self_assessed_level")

        raw_preferences = payload.get("preferences") or {}
        if not isinstance(raw_preferences, dict):
            raise ValueError("preferences must be a JSON object")
        duration = int(raw_preferences.get("session_duration_minutes", 30))
        if duration not in self.VALID_DURATIONS:
            raise ValueError("session_duration_minutes must be one of 15, 30, 45, 60")

        known_skill_note = self._text(payload.get("known_skill_note", ""))
        note_skills = [item.strip() for item in known_skill_note.replace("，", ",").split(",") if item.strip()]
        known_skills = self._unique_strings(payload.get("known_skill_ids", []), "known_skill_ids")
        activities = self._unique_strings(raw_preferences.get("activity_types", ["reading", "quiz"]), "activity_types")

        return LearnerProfile(
            user_id=user_id,
            learning_domain=learning_domain,
            background=background,
            self_assessed_level=level,
            known_skill_ids=list(dict.fromkeys([*known_skills, *note_skills])),
            known_skill_note="，".join(note_skills),
            preferences=LearningPreferences(
                activity_types=activities,
                content_style=self._enum(raw_preferences.get("content_style", "balanced"), self.VALID_CONTENT_STYLES, "content_style"),
                difficulty=self._enum(raw_preferences.get("difficulty", "adaptive"), self.VALID_DIFFICULTIES, "difficulty"),
                session_duration_minutes=duration,
                learning_frequency=self._enum(raw_preferences.get("learning_frequency", "flexible"), self.VALID_FREQUENCIES, "learning_frequency"),
            ),
            current_confusions=self._text(payload.get("current_confusions", "")),
            additional_requirements=self._text(payload.get("additional_requirements", "")),
        )

    def apply_corrections(self, draft: dict[str, Any], corrections: dict[str, Any]) -> LearnerProfile:
        if not isinstance(corrections, dict):
            raise ValueError("corrections must be a JSON object")
        merged = dict(draft)
        merged.update(corrections)
        if "preferences" in corrections:
            original_preferences = draft.get("preferences") or {}
            corrected_preferences = corrections.get("preferences") or {}
            if not isinstance(corrected_preferences, dict):
                raise ValueError("preferences must be a JSON object")
            merged["preferences"] = {**original_preferences, **corrected_preferences}
        return self.build_profile(merged)

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()

    def _required_text(self, payload: dict[str, Any], field: str) -> str:
        value = self._text(payload.get(field, ""))
        if not value:
            raise ValueError(f"{field} is required")
        return value

    def _enum(self, value: object, allowed: set[str], field: str) -> str:
        normalized = self._text(value)
        if normalized not in allowed:
            raise ValueError(f"unsupported {field}: {normalized}")
        return normalized

    def _unique_strings(self, value: object, field: str) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"{field} must be a list")
        return list(dict.fromkeys(item for item in (self._text(item) for item in value) if item))
