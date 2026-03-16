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

- Comando **`/estado_invitaciones`** (solo admin): lista todas las invitaciones por cupo de canciones con:
  - Usuario (ID y nombre si existe).
  - Canciones generadas y cupo total.
  - Cuántas le quedan disponibles.
  - Fecha de expiración de la invitación.

---

## Resumen de comandos

| Comando | Quién | Descripción |
|--------|--------|-------------|
| `/invite_songs <user_id> <cantidad> [horas]` | Admin | Invitar a un usuario con un cupo limitado de canciones. |
| `/grant_songs <user_id> <cantidad>` | Admin | Añadir más canciones al cupo de un usuario. |
| `/solicitar_canciones` | Invitados con cupo | Solicitar más canciones al administrador. |
| `/estado_invitaciones` | Admin | Ver estado de todas las invitaciones (generadas, restantes, expiración). |
| `/generate_song` | Usuario o invitado con cupo | Crear una canción (el invitado solo puede usar esto y solicitar más). |
| `/save_song` | Quien generó / Admin | Guardar la última canción en el servidor (el usuario guarda la suya; tú puedes guardar la copia que te enviamos). |

## Documentación técnica

Para más detalle del flujo, permisos y base de datos, ver el [README principal](../README.md) y la sección de invitaciones.
