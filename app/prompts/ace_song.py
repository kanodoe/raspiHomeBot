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
        "- \"style\": detailed musical style description in ENGLISH. "
        "Describe the genre, mood, tempo, and instruments with high detail. "
        "You MUST specify vocal characteristics (e.g., 'raw male vocals with breathy textures', 'intimate female lead', 'soft harmonies'). "
        "Include a dynamic arc for the arrangement (e.g., 'starts minimal with acoustic guitar, builds with subtle percussion and pedal steel swells, instrumental bridge with harmonica'). "
        "Focus on creating a vivid atmosphere (analog feel, spacious reverb, emotional nuance). "
        "All style descriptors must be in English.\n"
        "- \"lyrics\": the full song lyrics in " + language_name + ". "
        "You MUST mark every section header with square brackets, e.g. [Intro], [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]. "
        "Ensure section labels are ALWAYS inside []. Use line breaks between stanzas.\n"
        "Respond only with the JSON, no extra text, no markdown."
    )

# Default (e.g. Spanish) when no language specified
SYSTEM_PROMPT_STYLE_LYRICS = (
    "You are an expert song composer and music producer. "
    "Your task is to help the user create a song. "
    "You must respond ONLY with a valid JSON object with exactly two fields:\n"
    "- \"style\": detailed musical style description in ENGLISH. "
    "Describe genre, mood, tempo (BPM), and instruments. "
    "You MUST include specific vocal details (e.g., gender, texture, number of voices) and "
    "a detailed dynamic arrangement (how it starts, develops, and ends with specific instrument behavior). "
    "Aim for descriptive, atmospheric prose rather than just simple tags.\n"
    "- \"lyrics\": the full song lyrics in the language requested by the user. "
    "You MUST mark every section header with square brackets: [Intro], [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]. "
    "Ensure labels are ALWAYS inside []. Use line breaks between stanzas.\n"
    "Respond only with the JSON, no extra text, no markdown."
)

# When user chose "solo estilo" (instrumental): only style in English, no lyrics.
SYSTEM_PROMPT_STYLE_ONLY = (
    "You are an expert music producer. "
    "The user wants only a musical style description for an instrumental track (no lyrics). "
    "Respond ONLY with a valid JSON object with exactly two fields:\n"
    "- \"style\": concise musical style in ENGLISH as a single comma-separated string. Include genre, instruments, tempo, mood (e.g. cinematic orchestral, 90 BPM, dramatic). "
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
    "- \"style\": concise musical style description in ENGLISH as a single comma-separated string. "
    "Include genre, instruments, tempo, mood, and MANDATORY vocal details (male/female/duet/choir). "
    "Describe structure with intention: how the song begins, develops and ends. Use English tags.\n"
    "- \"lyrics\": the full song lyrics in the randomly chosen language. "
    "You MUST mark section headers with square brackets: [Intro], [Verse 1], [Chorus], etc. Labels must be ALWAYS inside [].\n"
    "- \"language\": the name of the randomly chosen language (e.g. \"Spanish\", \"Japanese\").\n"
    "- \"summary\": A very brief summary in SPANISH about the musical style and what the lyrics are about (1-2 sentences max). "
    "Example: 'Una canción de K-Pop energético sobre la libertad en Coreano' or 'Un jazz suave instrumental sobre una tarde lluviosa'. "
    "Do not give details, just the general idea.\n"
    "Respond only with the JSON, no extra text, no markdown."
)


# Language codes and display names (ACE-Step supports 50+; common set for the UI)
LYRICS_LANGUAGE_OPTIONS: List[Tuple[str, str]] = [
    ("en", "Inglés"),
    ("es", "Español"),
    ("fr", "Francés"),
    ("de", "Alemán"),
    ("it", "Italiano"),
    ("pt", "Portugués"),
    ("zh", "Chino"),
    ("ja", "Japonés"),
    ("ko", "Coreano"),
    ("ru", "Ruso"),
    ("ar", "Árabe"),
    ("hi", "Hindi"),
    ("tr", "Turco"),
    ("pl", "Polaco"),
    ("nl", "Neerlandés"),
    ("id", "Indonesio"),
    ("th", "Tailandés"),
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
            elif isinstance(v, dict):
                # Recursivamente aplanar diccionarios anidados
                flat_nested = _normalize_style(v)
                parts.append(flat_nested)
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
    if isinstance(value, dict):
        # Si el modelo devuelve un objeto {"Verse 1": "...", "Chorus": "..."}
        lines = []
        for k, v in value.items():
            # k es el nombre de la sección, v es el contenido
            lines.append(f"[{k}]")
            lines.append(str(v))
            lines.append("")
        return normalize_lyrics_sections("\n".join(lines))
    return normalize_lyrics_sections(str(value).strip())


def normalize_lyrics_sections(lyrics: str) -> str:
    """
    Asegura que todas las indicaciones de sección (Verse, Chorus, Intro, etc.)
    estén entre corchetes []. 
    Cubre casos como "Verse 1:", "Chorus -", "[Intro]", etc.
    """
    if not lyrics or not lyrics.strip():
        return lyrics

    lines = lyrics.split("\n")
    out = []
    
    # Lista de etiquetas comunes que el LLM podría usar como encabezado de sección
    tags = [
        "Intro", "Verse", "Verso", "Chorus", "Coro", "Bridge", "Puente", 
        "Outro", "Pre-Chorus", "Post-Chorus", "Interlude", "Refrain",
        "Solo", "Instrumental", "Hook", "Drop", "Breakdown", "Coda"
    ]
    tags_re = "|".join(tags)
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
            
        # Caso 1: La línea ES solo una etiqueta (posiblemente con número, y con : o - opcional al final)
        # Ej: "Verse 1", "Chorus:", "Bridge -"
        # Permitimos que ya tenga corchetes, pero los normalizamos
        match = re.match(
            rf"^\[?({tags_re})(?:\s*\d+)?\]?(?:\s*[:\-])?\s*$",
            stripped,
            re.IGNORECASE
        )
        if match:
            # Extraer solo la parte alfanumérica (etiqueta y número)
            clean_match = re.search(rf"({tags_re})(?:\s*\d+)?", stripped, re.IGNORECASE)
            if clean_match:
                label = clean_match.group(0).strip()
                # Capitalizar la primera letra para consistencia (opcional, pero queda mejor)
                label = label[0].upper() + label[1:] if label else label
                out.append(f"[{label}]")
                continue
            
        # Caso 2: La línea empieza con la etiqueta seguida de : o - y luego texto en la misma línea
        # Ej: "Verse 1: En un día de sol..." -> Convertir a "[Verse 1]\nEn un día de sol..."
        match = re.match(
            rf"^\[?({tags_re})(?:\s*\d+)?\]?(?:\s*[:\-]\s+)(.*)$",
            stripped,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            label_match = re.search(rf"({tags_re})(?:\s*\d+)?", stripped, re.IGNORECASE)
            label = label_match.group(0).strip() if label_match else match.group(1).strip()
            label = label[0].upper() + label[1:] if label else label
            
            rest = match.group(2).strip()
            out.append(f"[{label}]\n{rest}" if rest else f"[{label}]")
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
