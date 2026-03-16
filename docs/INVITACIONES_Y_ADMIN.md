# Invitaciones por cupo de canciones y funciones de administrador

## ¿Qué es posible y qué no?

### 1. ¿Cada usuario puede ver "su propia instancia" del bot?

**No**, en el sentido de tener un bot o un menú distinto por usuario.

En Telegram **un bot es una sola cuenta**: todos los usuarios hablan con el mismo bot. La API de Telegram **no permite** definir menús de comandos distintos por usuario: la lista de comandos que se muestra al escribir `/` es la misma para todo el mundo (o por tipo de chat: privado vs grupo).

Lo que **sí** hace el bot:

- **Permisos por usuario**: solo los autorizados pueden usar cada comando. Si un invitado escribe `/pc_on` o `/invite`, recibe "No tienes permiso".
- **Solo pueden generar canciones** (y solicitar más cupo) si tienen invitación con cupo; el resto de funciones del menú no les funcionan.

En la práctica, cada usuario "ve" un comportamiento distinto según su rol (admin, usuario completo, invitado por canciones), pero **no** un menú o una "instancia" visual distinta.

---

### 2. Avisos al administrador

- **Cuando un invitado "acepta" la invitación**: se considera aceptación la **primera vez** que usa `/generate_song`. En ese momento se te notifica: *"El usuario X ha empezado a usar su invitación (primera vez)."*
- **Cada vez que alguien genera una canción**: cuando la generación termina, recibes un mensaje privado con la copia de la canción (audio + JSON), indicando **quién la generó**, y puedes guardar audio y JSON en el servidor (solo tú; el usuario solo descarga el MP3).

---

### 3. Copia de la canción al admin y guardado

- **Tú recibes** en privado:
  - Un mensaje indicando **quién generó** la canción (nombre/usuario e ID).
  - El **audio** (MP3) como archivo.
  - El **JSON** devuelto por la API como documento descargable.
  - Un botón **"Guardar en servidor"** que guarda tanto el audio como el JSON en la carpeta configurada (por ejemplo `C:\telegram_songs`).
- **El usuario** solo recibe el MP3 en su chat (sin JSON ni opción de guardar en servidor).

---

### 4. Estado de invitaciones y canciones

- Comando **`/invitations_status`** (solo admin): lista todas las invitaciones por cupo de canciones con:
  - Usuario (ID y nombre si existe).
  - Canciones generadas y cupo total.
  - Cuántas le quedan disponibles.
  - Fecha de expiración de la invitación.

---

## Enlace de invitación (sin saber el ID)

Puedes invitar a alguien **sin saber su Telegram ID** usando un enlace. Hay dos comandos:

- **`/invite_link <cantidad>`** — Enlace por *cantidad de canciones* (acceso prolongado). Ej: `/invite_link 5`.
- **`/invite_link_hours <cantidad> <horas>`** — Enlace por *cantidad de canciones* y *duración del acceso en horas*. Ej: `/invite_link_hours 5 24` (5 canciones, acceso 24 h).

1. Escribe **`/invite_link 5`** o **`/invite_link_hours 5 48`** (según quieras solo cantidad o cantidad + horas).
2. El bot te enviará **solo a ti** (por mensaje privado) un enlace. Si escribes el comando en un grupo, el enlace no se muestra en el grupo.
3. Envía ese enlace a la persona (por Telegram, WhatsApp, etc.).
4. Cuando **ella abra el enlace**, se abrirá el bot y se creará automáticamente su invitación con esas canciones (y, si usaste `invite_link_hours`, con la duración en horas). Tú recibirás un aviso: *"El usuario X ha usado tu enlace de invitación y tiene N canciones."*

No hace falta que tengas a la persona en la lista del bot ni que sepas su ID.

### Seguridad del enlace

El valor del enlace va **cifrado** (Fernet). Así nadie puede cambiar el número editando la URL. Si se define `INVITE_LINK_SECRET` en el `.env`, se usa para cifrar; si no, se usa el token del bot admin (para que admin codifique y los bots de canciones/portón decodifiquen con el mismo valor).

**Formato del payload (interno, cifrado):**
- **Canciones (solo cantidad):** `{"t": "songs", "c": N}` — acceso prolongado. Opcionales: `"exp"`, `"n"`.
- **Canciones (cantidad + horas):** `{"t": "songs", "c": N, "h": H}` — el acceso del invitado dura H horas. Opcionales: `"exp"`, `"n"`.
- **Portón:** `{"t": "gate", "d": N}` (días de acceso), con opcionales `"exp"` y `"n"`.

---

## Invitación al portón (otro bot)

El **portón** puede estar controlado por **otro bot** (o servicio). Este proyecto no tiene acceso directo a ese bot; en su lugar:

1. **Invitación por días:** Con `/gate_invite <user_id> <días>` o `/gate_invite_link <días>` (enlace cifrado que te envían por privado) das a alguien acceso al portón durante N días.
2. **Uso:** El invitado escribe **`/gate_open`** en *este* bot. Este bot comprueba que tiene invitación de portón activa y entonces **envía una petición al servicio del portón** (proxy), de forma que el otro bot/servicio abre el portón **como si lo hubieras pedido tú** (autorizado por secreto compartido).
3. **Configuración:** En `.env` defines `GATE_PROXY_URL` (endpoint al que este bot hace POST) y `GATE_PROXY_SECRET`. El otro proyecto (el bot del portón o un servicio intermedio) debe exponer un endpoint que acepte POST con ese secreto y, opcionalmente, `guest_telegram_id` y `admin_telegram_id`, y entonces ejecute la apertura del portón.

Así se separan responsabilidades: este proyecto solo **configura** invitaciones y **reenvía** la orden al proxy; el bot/servicio del portón es quien realmente abre. Si prefieres que un **segundo bot** (proxy) reciba la orden y hable con el bot del portón, puedes desplegar ese proxy y poner su URL en `GATE_PROXY_URL`; la configuración de invitaciones sigue siendo esta misma.

---

## Resumen de comandos

| Comando | Quién | Descripción |
|--------|--------|-------------|
| `/invite_link <cantidad>` | Admin | Enlace por cantidad de canciones (acceso prolongado); te lo envía por privado. |
| `/invite_link_hours <cantidad> <horas>` | Admin | Enlace por cantidad de canciones y duración del acceso en horas; te lo envía por privado. |
| `/gate_invite_link <días>` | Admin | Enlace de invitación al portón (días); te lo envía por privado. |
| `/gate_invite <user_id> <días>` | Admin | Invitación al portón por ID y número de días. |
| `/invite_songs <user_id> <cantidad> [horas]` | Admin | Invitar por ID con cupo de canciones. |
| `/grant_songs <user_id> <cantidad>` | Admin | Añadir más canciones al cupo de un usuario. |
| `/request_songs` | Invitados con cupo | Solicitar más canciones al administrador. |
| `/invitations_status` | Admin | Ver estado de invitaciones (canciones). |
| `/gate_open` | Usuario o invitado portón | Abrir el portón (invitados: vía proxy al otro bot). |
| `/generate_song` | Usuario o invitado con cupo | Crear una canción. |
| `/save_song` | Quien generó / Admin | Guardar la última canción en el servidor. |

## Documentación técnica

Para más detalle del flujo, permisos y base de datos, ver el [README principal](../README.md) y la sección de invitaciones.

---

## Modo multi-bot y base de datos

El proyecto puede ejecutarse en tres modos (`BOT_MODE` en `.env`: `admin`, `songs`, `gate`), compartiendo la misma base de datos. Cada proceso puede usar su propio token: `BOT_TOKEN_ADMIN`, `BOT_TOKEN_SONGS`, `BOT_TOKEN_GATE`; si no está definido el del modo, se usa `BOT_TOKEN`.

- **admin**: Bot de administración y servicios (PC, ACE-Step, Ollama, invitaciones, estado). Genera enlaces que abren el bot de canciones o el de portón según `SONGS_BOT_USERNAME` y `GATE_BOT_USERNAME`.
- **songs**: Solo `/start` (con enlace de invitación), `/generate_song` y `/request_songs`. Para usuarios con cupo de canciones.
- **gate**: Solo `/start` (con enlace de portón), `/gate_open`, `/entrada` (E) y `/salida` (S). Si está configurado `PORTON_CHANNEL_ID`, envía "E" o "S" a ese canal (PortonBot); si no, usa proxy o bus como antes.

### Entidades de la base de datos

- **User**: usuarios (telegram_id, username, first_name, last_name, role, created_at).
- **Invitation**: acto de invitar (inviter, invitee, registered_at, access_type: song | gate).
- **UserQuota**: cuotas por usuario y tipo de acción (song: song_quota/songs_used; gate: gate_expires_at).
- **UserOperation**: registro de operaciones (gate_opened, song_generated) con fecha y opcional display_name.
- **AccessRequest**: solicitudes de más acceso (pending/approved/denied, responded_at, responded_by).

### API de consulta

Endpoints GET de solo lectura: `/api/users`, `/api/invitations`, `/api/quotas`, `/api/operations`, `/api/access-requests`. Opcionalmente protegidos con `API_KEY` (header `X-Api-Key`). Ver [API.md](API.md) e importar la colección Postman/Bruno desde `docs/api/raspiHomeBot-api.postman_collection.json`.
