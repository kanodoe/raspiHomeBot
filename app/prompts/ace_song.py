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
        "Also describe structure: how the song begins (intro: sparse, full, fade-in), how it develops (verses, build-up, climax), and how it ends (outro, fade-out, big finish). "
        "Use English tags and descriptors so the music model can use them.\n"
        "- \"lyrics\": the full song lyrics in " + language_name + ". "
        "Use clear structure: mark every section with square brackets, e.g. [Intro], [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]. "
        "Use line breaks between stanzas. The lyrics must be creative and match the style.\n"
        "Respond only with the JSON, no extra text, no markdown."
    )

# Default (e.g. Spanish) when no language specified
SYSTEM_PROMPT_STYLE_LYRICS = (
    "You are an expert song composer and music producer. "
    "Your task is to help the user create a song. "
    "You must respond ONLY with a valid JSON object with exactly two fields:\n"
    "- \"style\": concise musical style description in ENGLISH (genre, instruments, tempo, mood). "
    "Include how the song begins (intro), develops (build-up, climax) and ends (outro, fade or big finish). Use English tags for the music model.\n"
    "- \"lyrics\": the full song lyrics in the language requested by the user. "
    "Mark every section with square brackets: [Intro], [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]. Use line breaks between stanzas.\n"
    "Respond only with the JSON, no extra text, no markdown."
)

# When user chose "solo estilo" (instrumental): only style in English, no lyrics.
SYSTEM_PROMPT_STYLE_ONLY = (
    "You are an expert music producer. "
    "The user wants only a musical style description for an instrumental track (no lyrics). "
    "Respond ONLY with a valid JSON object with exactly two fields:\n"
    "- \"style\": concise musical style in ENGLISH. Include genre, instruments, tempo, mood (e.g. cinematic orchestral, 90 BPM, dramatic). "
    "Describe structure: how it begins (intro), develops and ends (outro or climax). Use English tags so the music model can use them.\n"
    "- \"lyrics\": leave empty string \"\".\n"
    "Respond only with the JSON, no extra text, no markdown."
)


# When the user wants a completely random song (assisted by AI)
SYSTEM_PROMPT_RANDOM_SONG = (
    "You are an expert song composer and music producer. "
    "Your task is to create a COMPLETELY RANDOM song. "
    "Choose a random musical genre (e.g. heavy metal, k-pop, bossa nova, synthwave, country, etc.), "
    "a random theme/topic, and a random language from around the world (e.g. Japanese, Italian, Spanish, English, etc.). "
    "You must respond ONLY with a valid JSON object with exactly four fields:\n"
    "- \"style\": concise musical style description in ENGLISH (genre, instruments, tempo, mood). "
    "Include how the song begins, develops and ends. Use English tags for the music model.\n"
    "- \"lyrics\": the full song lyrics in the randomly chosen language. "
    "Mark sections with square brackets: [Intro], [Verse 1], [Chorus], etc.\n"
    "- \"language\": the name of the randomly chosen language (e.g. \"Spanish\", \"Japanese\").\n"
    "- \"summary\": A very brief summary in SPANISH about the musical style and what the lyrics are about (1-2 sentences max). "
    "Example: 'Una canción de K-Pop energético sobre la libertad en Coreano' or 'Un jazz suave instrumental sobre una tarde lluviosa'. "
    "Do not give details, just the general idea.\n"
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
        return normalize_lyrics_sections(value.strip())
    return normalize_lyrics_sections(str(value).strip())


def normalize_lyrics_sections(lyrics: str) -> str:
    """
    Asegura que todas las indicaciones de sección (Verse, Chorus, Intro, etc.)
    estén entre corchetes []. Si aparecen como "Verse 1:" o "Chorus:", se convierten a [Verse 1], [Chorus].
    """
    if not lyrics or not lyrics.strip():
        return lyrics

    lines = lyrics.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        # Si la línea es solo una etiqueta de sección (con o sin : o -), envolver en []
        match = re.match(
            r"^(Intro|Verse\s*\d*|Verso\s*\d*|Chorus|Coro|Bridge|Puente|Outro|Pre-Chorus|Post-Chorus|Interlude|Refrain)(?:\s*[:\-])?\s*$",
            stripped,
            re.IGNORECASE,
        )
        if match:
            label = match.group(1).strip()
            if not (label.startswith("[") and label.endswith("]")):
                out.append(f"[{label}]")
            else:
                out.append(line)
            continue
        # Si la línea empieza por etiqueta seguida de dos puntos o guión y luego texto, poner etiqueta en []
        match = re.match(
            r"^(Intro|Verse\s*\d*|Verso\s*\d*|Chorus|Coro|Bridge|Puente|Outro|Pre-Chorus|Post-Chorus|Interlude|Refrain)(?:\s*[:\-]\s*)(.*)$",
            stripped,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            label, rest = match.group(1).strip(), match.group(2).strip()
            if not (label.startswith("[") and label.endswith("]")):
                out.append(f"[{label}]\n{rest}" if rest else f"[{label}]")
            else:
                out.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def _extract_first_json_object(text: str) -> Optional[str]:
    """Extrae el primer objeto JSON válido (de { a la } que cierra). Evita capturar de más con .* greedy."""
    if not text or "{" not in text:
        return None
    start = text.index("{")
    depth = 0
    in_string = False
    escape = False
    quote_char = None
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if in_string:
            if c == quote_char:
                in_string = False
            continue
        if c in ('"', "'"):
            in_string = True
            quote_char = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_style_lyrics_response(response_text: str) -> Dict[str, str]:
    """
    Parsea la respuesta del LLM en un diccionario con 'style', 'lyrics' y opcionalmente 'summary'.

    Tolerates markdown code blocks and extra text; extracts the first JSON object found.
    Si el modelo devuelve "style" como objeto (p. ej. genre, instruments, tempo, mood),
    se convierte a una sola línea para ACE-Step.
    Si falla el parseo, se usa estilo por defecto y el texto crudo como letra en lugar de mostrar error.
    """
    if not response_text or not response_text.strip():
        return {"style": "Pop rock", "lyrics": "", "summary": "", "language": ""}

    # Quitar posibles bloques markdown ```json ... ```
    text = response_text.strip()
    for pattern in (r"```(?:json)?\s*", r"```\s*$"):
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = text.strip()

    try:
        raw = _extract_first_json_object(text)
        if raw:
            data = None
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Respuesta truncada: intentar cerrar llaves
                if raw.count("{") > raw.count("}"):
                    for _ in range(5):
                        raw += "}"
                        try:
                            data = json.loads(raw)
                            break
                        except json.JSONDecodeError:
                            continue
            if data is not None:
                style = _normalize_style(data.get("style"))
                lyrics = _normalize_lyrics(data.get("lyrics"))
                summary = str(data.get("summary") or "").strip()
                language = str(data.get("language") or "").strip()
                if style and "Error" not in style:
                    return {"style": style, "lyrics": lyrics, "summary": summary, "language": language}
    except (KeyError, TypeError):
        pass

    # Fallback: no mostrar "Error parseando"; usar estilo por defecto y texto como letra si parece contenido
    style_fallback = "Pop rock"
    if '"style"' in text or "'style'" in text:
        m = re.search(r'["\']style["\']\s*:\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
        if m:
            style_fallback = _normalize_style(m.group(1)) or style_fallback
    return {
        "style": style_fallback,
        "lyrics": text if len(text) > 20 else "",
        "summary": "",
        "language": ""
    }
