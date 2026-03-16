"""
Prompts for generating musical style and lyrics in the format expected by ACE-Step.

ACE-Step release_task (text2music) expects:
- prompt: description of musical style (instruments, tempo, genre, mood)
- lyrics: full song lyrics (verses, chorus, etc.)

Use these prompts with any LLM (Ollama, OpenAI, etc.) to produce a JSON with
'style' and 'lyrics' that can be sent to ACE-Step.
"""

import json
import re
from typing import Dict, Optional

# System prompt: instructs the model to output JSON with 'style' and 'lyrics'
SYSTEM_PROMPT_STYLE_LYRICS = (
    "Eres un experto compositor de canciones y productor musical. "
    "Tu tarea es ayudar al usuario a crear una canción. "
    "Debes responder ÚNICAMENTE con un objeto JSON válido que tenga exactamente dos campos:\n"
    "- \"style\": descripción concisa del estilo musical para la generación. Incluye género, "
    "instrumentos, tempo, ambiente o mood (ej: rock alternativo, batería marcada, guitarra eléctrica, 120 BPM, intenso). "
    "Esta descripción será usada por el modelo de música para definir el sonido.\n"
    "- \"lyrics\": la letra completa de la canción, con versos y estribillo claros. "
    "Puedes usar saltos de línea para separar estrofas. La letra debe ser creativa y coherente con el estilo.\n"
    "Responde solo el JSON, sin texto adicional, sin markdown ni explicaciones."
)


def build_user_prompt(tema: str, refinamiento: Optional[str] = None) -> str:
    """
    Build the user prompt for style + lyrics generation.

    Args:
        tema: User's theme or instructions (e.g. "una canción de rock sobre un robot").
        refinamiento: Optional refinement (e.g. "haz el estilo más suave" or "cambia el estribillo").

    Returns:
        User prompt string to send to the LLM.
    """
    if refinamiento:
        return (
            f"Crea una canción basada en: {tema}\n\n"
            f"Refinamiento o cambio solicitado: {refinamiento}"
        )
    return f"Crea una canción basada en el siguiente tema o indicaciones: {tema}"


def parse_style_lyrics_response(response_text: str) -> Dict[str, str]:
    """
    Parse the LLM response into a dict with 'style' and 'lyrics'.

    Tolerates markdown code blocks and extra text; extracts the first JSON object found.

    Args:
        response_text: Raw response from the LLM.

    Returns:
        Dict with keys 'style' and 'lyrics'. If parsing fails, returns a fallback
        with 'style' set to a generic value and 'lyrics' to the raw text.
    """
    if not response_text or not response_text.strip():
        return {"style": "Pop rock", "lyrics": ""}

    try:
        # Find JSON object (possibly wrapped in markdown or extra text)
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return {
                "style": data.get("style", "Pop rock"),
                "lyrics": data.get("lyrics", ""),
            }
    except (json.JSONDecodeError, KeyError):
        pass  # fallback below

    return {
        "style": "Error parseando respuesta de IA",
        "lyrics": response_text,
    }
