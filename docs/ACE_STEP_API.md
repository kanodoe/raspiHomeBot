# Referencia de API ACE-Step 1.5

ACE-Step 1.5 expone una API REST (normalmente en el puerto 8001) que permite la generación de música a partir de texto.

## Endpoints Principales

### 1. `POST /release_task`
Envía una tarea de generación a la cola.

**Cuerpo (JSON):**
- `task_type`: `"text2music"` (para generación a partir de estilo y letra).
- `prompt`: (String) Descripción del estilo musical. Se recomienda usar etiquetas en inglés separadas por comas (ej: `"pop, upbeat, 120bpm, male voice"`).
- `lyrics`: (String) Letra de la canción. Para mejores resultados, marcar las secciones con corchetes: `[Intro]`, `[Verse 1]`, `[Chorus]`, etc.
- `thinking`: (Boolean) `true` para usar el modelo con razonamiento.
- `use_format`: (Boolean) `true`.
- `gpt_description_prompt`: (String) Duplicar aquí el contenido de `prompt`.

**Respuesta:**
```json
{
  "code": 200,
  "data": {
    "task_id": "uuid-de-la-tarea"
  }
}
```

### 2. `POST /query_result`
Consulta el estado de una o varias tareas.

**Cuerpo (JSON):**
- `task_id_list`: (String) Lista de IDs serializada como string, ej: `'["uuid1"]'`.

**Respuesta (Estados):**
- `0`: Procesando (`processing`)
- `1`: Completado (`completed`)
- `2` o `-1`: Fallido (`failed`)

### 3. `GET /v1/audio`
Descarga el audio generado.

**Parámetros:**
- `path`: Ruta del archivo obtenida del resultado de la tarea.

## Notas de Implementación
- El bot aplanará automáticamente cualquier estructura JSON devuelta por el LLM para el campo `style` en una cadena de etiquetas separadas por comas.
- Las letras devueltas como objeto JSON también serán convertidas al formato de secciones `[Etiqueta]` requerido.
- La comunicación se realiza vía HTTP (si el servicio escucha en `0.0.0.0`) y el control de procesos vía SSH.
