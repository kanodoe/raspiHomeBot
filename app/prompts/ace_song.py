"""
Prompts for generating musical style and lyrics in the format expected by ACE-Step.

ACE-Step release_task (text2music) expects:
- prompt: description of musical style in English (tags, genre, instruments, tempo)
- lyrics: full song lyrics (verses, chorus, etc.) in the requested language

Use these prompts with any LLM (Ollama, OpenAI, etc.) to produce a JSON with
'style' and 'lyrics' that can be sent to ACE-Step.
"""

import json
import re
from typing import Dict, List, Optional, Tuple

# System prompt when we want style + lyrics. Style/tags must be in English; lyrics in the requested language.
def get_system_prompt_style_lyrics(language_name: str) -> str:
    return (
        "You are an expert song composer and music producer. "
        "Your task is to help the user create a song. "
        "You must respond ONLY with a valid JSON object with exactly two fields:\n"
        "- \"style\": concise musical style description for generation, in ENGLISH. "
        "Include genre, instruments, tempo, mood (e.g. alternative rock, punchy drums, electric guitar, 120 BPM, intense). "
        "Use English tags and descriptors so the music model can use them.\n"
        "- \"lyrics\": the full song lyrics in " + language_name + ". "
        "Use clear verses and chorus; use line breaks between stanzas. "
        "The lyrics must be creative and match the style.\n"
        "Respond only with the JSON, no extra text, no markdown."
    )

# Default (e.g. Spanish) when no language specified
SYSTEM_PROMPT_STYLE_LYRICS = (
    "You are an expert song composer and music producer. "
    "Your task is to help the user create a song. "
    "You must respond ONLY with a valid JSON object with exactly two fields:\n"
    "- \"style\": concise musical style description in ENGLISH (genre, instruments, tempo, mood). "
    "Use English tags for the music model.\n"
    "- \"lyrics\": the full song lyrics in the language requested by the user. "
    "Use clear verses and chorus; use line breaks between stanzas.\n"
    "Respond only with the JSON, no extra text, no markdown."
)

# When user chose "solo estilo" (instrumental): only style in English, no lyrics.
SYSTEM_PROMPT_STYLE_ONLY = (
    "You are an expert music producer. "
    "The user wants only a musical style description for an instrumental track (no lyrics). "
    "Respond ONLY with a valid JSON object with exactly two fields:\n"
    "- \"style\": concise musical style in ENGLISH. Include genre, instruments, tempo, mood (e.g. cinematic orchestral, 90 BPM, dramatic). "
    "Use English tags so the music model can use them.\n"
    "- \"lyrics\": leave empty string \"\".\n"
    "Respond only with the JSON, no extra text, no markdown."
)


# Language codes and display names (ACE-Step supports 50+; common set for the UI)
LYRICS_LANGUAGE_OPTIONS: List[Tuple[str, str]] = [
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("zh", "中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ru", "Русский"),
    ("ar", "العربية"),
    ("hi", "हिन्दी"),
    ("tr", "Türkçe"),
    ("pl", "Polski"),
    ("nl", "Nederlands"),
    ("id", "Indonesia"),
    ("th", "ไทย"),
]


def get_language_name(code: str) -> str:
    """Return display name for a language code, or the code itself."""
    for c, name in LYRICS_LANGUAGE_OPTIONS:
        if c == code:
            return name
    return code


def build_user_prompt(
    tema: str,
    refinamiento: Optional[str] = None,
    language_name: Optional[str] = None,
    style_only: bool = False,
) -> str:
    """
    Build the user prompt for style and/or lyrics generation.

    Args:
        tema: User's theme or instructions.
        refinamiento: Optional refinement (e.g. "haz el estilo más suave").
        language_name: Name of the language for lyrics (e.g. "Español"). If set, we ask for lyrics in that language.
        style_only: If True, only ask for style (no lyrics).

    Returns:
        User prompt string to send to the LLM.
    """
    if style_only:
        base = f"Describe only the musical style for an instrumental track (no lyrics). Theme or mood: {tema}"
        if refinamiento:
            return f"{base}\n\nRefinement: {refinamiento}"
        return base
    if refinamiento:
        out = f"Create a song based on: {tema}\n\nRefinement: {refinamiento}"
    else:
        out = f"Create a song based on: {tema}"
    if language_name:
        out += f"\n\nWrite the lyrics in {language_name}. The style/tags must be in English."
    return out


def _normalize_style(value) -> str:
    """Convierte style a string. Si el modelo devuelve un objeto (genre, instruments, tempo, mood), lo aplana en una línea para ACE-Step."""
    if value is None:
        return "Pop rock"
    if isinstance(value, str):
        return value.strip() or "Pop rock"
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if v is None:
                continue
            if isinstance(v, list):
                parts.append(" ".join(str(x) for x in v))
            else:
                parts.append(str(v))
        return ", ".join(parts).strip() or "Pop rock"
    return str(value).strip() or "Pop rock"


def _normalize_lyrics(value) -> str:
    """Asegura que lyrics sea un string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def parse_style_lyrics_response(response_text: str) -> Dict[str, str]:
    """
    Parse the LLM response into a dict with 'style' and 'lyrics'.

    Tolerates markdown code blocks and extra text; extracts the first JSON object found.
    Si el modelo devuelve "style" como objeto (p. ej. genre, instruments, tempo, mood),
    se convierte a una sola línea para ACE-Step.
    """
    if not response_text or not response_text.strip():
        return {"style": "Pop rock", "lyrics": ""}

    try:
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            raw = match.group(0)
            data = None
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Respuesta truncada: intentar cerrar llaves y comillas
                if raw.count("{") > raw.count("}"):
                    for _ in range(5):
                        raw += "}"
                        try:
                            data = json.loads(raw)
                            break
                        except json.JSONDecodeError:
                            continue
            if data is not None:
                return {
                    "style": _normalize_style(data.get("style")),
                    "lyrics": _normalize_lyrics(data.get("lyrics")),
                }
    except (KeyError, TypeError):
        pass

    return {
        "style": "Error parseando respuesta de IA",
        "lyrics": response_text,
    }
