# API de RaspiHomeBot

## Base URL

Por defecto el servicio expone la API en `http://192.168.1.220:8000`. En producción usa la URL de tu servidor.

## Autenticación (opcional)

Si en `.env` defines `API_KEY`, los endpoints de consulta de la base de datos requieren el header:

- **X-Api-Key**: valor de `API_KEY`

Si no defines `API_KEY`, los endpoints de consulta no exigen autenticación (solo accesibles en la red donde corre el servicio).

## Endpoints de sistema y control

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Verifica que el servicio está activo |
| `/status` | GET | Estado del PC (WOL) y del sistema |
| `/pc/on` | POST | Enciende el PC mediante Wake-on-LAN |
| `/pc/off` | POST | Apaga el PC mediante SSH |
| `/api/gate/open` | POST | Abre el portón (requiere secret) |
| `/logs` | GET | Lista los archivos de log de respaldo existentes |
| `/logs/{filename}` | GET | Descarga un archivo de log comprimido |

## Endpoints de consulta (solo lectura)

Todos bajo el prefijo `/api`, método GET.

| Endpoint | Descripción | Query params (opcionales) |
|----------|-------------|----------------------------|
| `GET /api/users` | Lista usuarios | `telegram_id`, `role`, `limit`, `offset` |
| `GET /api/users/{telegram_id}` | Detalle de un usuario | — |
| `GET /api/invitations` | Lista invitaciones | `access_type`, `invitee_telegram_id`, `expired`, `limit`, `offset` |
| `GET /api/invitations/{id}/leave-message` | Mensaje de salida para el invitee (revocación / no uso) | — |
| `DELETE /api/invitations/{id}` | Revoca invitación por id (elimina invitación y cuota asociada) | — |
| `POST /api/invitations/{id}/register-guest` | Crea/actualiza User GUEST para el invitee (para que aparezca en usuarios) | — |
| `GET /api/quotas` | Lista cuotas por usuario/acción | `telegram_id`, `access_type`, `limit`, `offset` |
| `GET /api/operations` | Lista operaciones (gate_opened, song_generated) | `telegram_id`, `operation_type`, `since`, `until`, `limit`, `offset` |
| `GET /api/access-requests` | Lista solicitudes de más acceso | `status`, `telegram_id`, `limit`, `offset` |
| `POST /api/register-guest` | Registra invitado con cuota y le notifica | (Body JSON: `telegram_id`, `song_quota`, `username`?, `first_name`?, `last_name`?) |

## Colección Postman / Bruno

En `docs/api/raspiHomeBot-api.postman_collection.json` tienes una colección Postman v2.1 con todas las peticiones de consulta y control.

### Cómo importar

1. **Postman**: File → Import → sube el archivo `raspiHomeBot-api.postman_collection.json`. Ajusta las variables de colección `base_url` (p. ej. `http://192.168.1.220:8000`) y, si usas API key, `api_key`.
2. **Bruno**: File → Import → Postman → selecciona el mismo JSON. Configura `base_url` y `api_key` en las variables de la colección.

### Variables de colección

- **base_url**: URL base del servicio (p. ej. `http://192.168.1.220:8000`).
- **api_key**: Si está definido `API_KEY` en el servidor, pon aquí el mismo valor y activa el header `X-Api-Key` en cada request (en la colección viene desactivado por defecto para entornos sin API key).

## Gestión de invitaciones

- **`GET /api/invitations/{id}/leave-message`**: Devuelve un mensaje de salida para enviar al invitado cuando se revoca la invitación o no se usa, junto con `invitee_telegram_id`, `invitee_display`, etc., para que el admin sepa a quién enviarlo.
- **`DELETE /api/invitations/{id}`**: Revoca la invitación con ese id (elimina la fila de invitación y la cuota UserQuota asociada). El invitado pierde el acceso. Responde 204 si existía, 404 si no.
- **`POST /api/invitations/{id}/register-guest`**: Crea o actualiza el usuario (User con role GUEST) para el invitee de esa invitación. Sirve para que un invitado que ya tiene invitación en la BD pero no aparecía en “usuarios registrados” pase a aparecer y pueda usar el sistema (p. ej. invitaciones creadas antes de tener `ensure_guest` al abrir el enlace).
- **`POST /api/register-guest`**: Crea un usuario GUEST y le asigna una cuota de canciones directamente, notificándole por Telegram. Requiere el ID de Telegram y la cantidad de canciones.

## Otros endpoints

- `POST /api/gate/open`: proxy del portón. Requiere body `{"secret": "GATE_PROXY_SECRET"}` o header `Authorization: Bearer <GATE_PROXY_SECRET>`. Solo tiene sentido cuando el proceso corre en modo admin y está configurado `GATE_PROXY_SECRET`.
