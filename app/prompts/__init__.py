# Prompts for LLM-based song style and lyrics generation (ACE-Step compatible).

from app.prompts.ace_song import (
    LYRICS_LANGUAGE_OPTIONS,
    SYSTEM_PROMPT_STYLE_LYRICS,
    SYSTEM_PROMPT_STYLE_ONLY,
    build_user_prompt,
    get_language_name,
    get_system_prompt_style_lyrics,
    normalize_lyrics_sections,
    parse_style_lyrics_response,
)

__all__ = [
    "LYRICS_LANGUAGE_OPTIONS",
    "SYSTEM_PROMPT_STYLE_LYRICS",
    "SYSTEM_PROMPT_STYLE_ONLY",
    "build_user_prompt",
    "get_language_name",
    "get_system_prompt_style_lyrics",
    "normalize_lyrics_sections",
    "parse_style_lyrics_response",
]
