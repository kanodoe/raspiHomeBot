# RaspiHomeBot — Contexto para agentes IA

Este documento describe el proyecto para que los agentes (Cursor, Copilot, etc.) puedan generar cambios o nuevas funcionalidades con contexto suficiente.

## Descripción del proyecto

- **RaspiHomeBot** es un sistema de automatización del hogar que se ejecuta en una Raspberry Pi (o en un contenedor). Se controla por **Telegram** (bot) y por una **API REST** (FastAPI).
- Incluye: encendido/apagado del PC (WOL, SSH), control de portón, permisos (RBAC), y **generación de música** mediante **ACE-Step 1.5** (API REST) y **Ollama** (sugerencias de estilo y letra).
- Referencia externa: [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5).

## Arquitectura de alto nivel

- **Event Bus** (interno): los módulos se comunican por eventos (publicar/suscribir). No hay llamadas directas entre módulos de dominio.
- **Flujo típico:** Usuario envía comando en Telegram → handler publica `command` con `command` y `source` → **CommandRouter** traduce a eventos concretos (`cmd.acestep.start`, `cmd.ollama.start`, etc.) → los controladores (p. ej. **AceStepController**) reaccionan y llaman a **servicios** (AceStepService, OllamaService) → los servicios usan HTTP, SSH o subprocess según el caso → se publican eventos de notificación (`notify.status`, `notify.error`, `notify.audio`) → **Notifier** envía el mensaje al chat de Telegram.
- **Módulos principales:** `CommandRouter`, `AceStepController`, `Notifier`, `StateStore`, `PCController`, `GateController`, `PermissionController`; opcionales: `ZigbeeAdapter`, `ArloAdapter`, `SchedulerModule`.

## Dónde está la lógica importante

| Área | Ubicación | Notas |
|------|-----------|--------|
| ACE-Step (arranque, parada, generación, guardado) | `app/services/acestep_service.py` | `start_api()` devuelve `(bool, Optional[str])`. No mata el proceso si el puerto ya está en uso en el remoto. |
| Ollama (disponibilidad, arranque, parada, sugerencias) | `app/services/ollama_service.py` | `start_ollama()` devuelve `(bool, Optional[str])`. Mismo criterio: no matar si el puerto está en uso. |
| Control de flujo ACE/Ollama/canción | `app/modules/acestep_controller.py` | Suscrito a `cmd.acestep.*` y `cmd.ollama.*`; publica `notify.*`. |
| SSH (ejecución de comandos en el host) | `app/utils/ssh.py` | `run_ssh_command(command, host)` usa `settings.SSH_PORT` (por defecto 22). |
| Handlers de Telegram (incl. flujo crear canción) | `app/bot/handlers.py` | `generate_song_mode` intenta arrancar Ollama si el usuario elige “Asistido por IA” y no está disponible. |
| Prompts para estilo y letra (ACE + cualquier LLM) | `app/prompts/` | `ace_song.py`: `SYSTEM_PROMPT_STYLE_LYRICS`, `build_user_prompt()`, `parse_style_lyrics_response()`. Usados por `OllamaService.suggest_song_details()`. |
| Configuración | `app/core/config.py`, `.env` | `PC_IP`, `SSH_USER`, `SSH_KEY_PATH`, `SSH_PORT`, `ACESTEP_*`, `OLLAMA_*`, `ENABLED_MODULES`. |

## Escenario: bot en contenedor, ACE y Ollama en Windows remoto

- El bot corre en Linux (contenedor); ACE-Step y Ollama corren en un PC Windows. La comunicación con el host es por **HTTP** (cuando los servicios escuchan en `0.0.0.0`) y por **SSH** (para arrancar/parar procesos).
- **Detección:** “¿Está la API lista?” se hace por **HTTP** (p. ej. `GET` a `ACESTEP_HOST:8001` o `OLLAMA_BASE_URL/api/tags`). Si el servicio en Windows está vinculado a `127.0.0.1`, el contenedor no puede conectarse y la comprobación falla.
- **Puerto en uso:** Si, vía SSH, se detecta que el puerto (8001 o 11434) está en uso en el host, el bot **no** debe matar ese proceso. Debe devolver error con un mensaje claro para el usuario (configurar `HOST=0.0.0.0` en `start_api_server_docker_remote.bat` o `OLLAMA_HOST=0.0.0.0`, y firewall). Esta regla ya está implementada en `AceStepService.start_api()` y `OllamaService.start_ollama()`.

## Prompts y formato ACE-Step

- Los prompts para generar **estilo** y **letra** están en `app/prompts/ace_song.py`. El formato de salida (JSON con `style` y `lyrics`) es el que ACE-Step espera en `release_task` (text2music): `prompt` = estilo, `lyrics` = letra.
- Cualquier integración con otro LLM (no solo Ollama) debería usar estos mismos prompts (`SYSTEM_PROMPT_STYLE_LYRICS`, `build_user_prompt`, `parse_style_lyrics_response`) para mantener compatibilidad con ACE-Step.

## Convenciones

- **Event Bus:** eventos conocidos incluyen `command`, `cmd.acestep.start`/`stop`/`generate`/`save`, `cmd.ollama.start`/`stop`, `notify.status`, `notify.error`, `notify.audio`, `notify.info`.
- **Origen de notificaciones:** `source` suele ser `chat_<chat_id>` para enviar la respuesta al chat correcto.
- **Configuración:** leer de `app.core.config.settings`; opcionalmente `config.yaml` para intervalos y `SSH_PORT`.
