from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from app.core.config import get_invite_link_secret
from app.core.logging import logger
from app.database.models import UserRole
from app.database.session import AsyncSessionLocal
from app.services.permission_service import PermissionService
from app.services.wol_service import WOLService
from app.services.gate_service import GateService
from app.services.pc_monitor_service import PCMonitorService
from app.services.ollama_service import OllamaService
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, filters

# Conversation states for generate_song
MODE_SELECT, STYLE, LYRICS_CHOICE, LYRICS_TEXT, AI_PROMPT, AI_REVIEW, LYRICS_OR_STYLE, AI_LANGUAGE = range(8)

def restricted(role: UserRole):
    def decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            async with AsyncSessionLocal() as session:
                permission_service = PermissionService(session)
                if not await permission_service.is_authorized(user_id, role):
                    logger.warning(f"Unauthorized access attempt by {user_id}")
                    msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
                    text = "No tienes permiso para usar este comando."
                    if msg and hasattr(msg, "reply_text"):
                        await msg.reply_text(text)
                    elif update.effective_chat:
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
                    return
            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator


def restricted_to_song(func):
    """Permite USER, ADMIN o invitados con cupo de canciones. Si cupo agotado, indica solicitar más."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            if await permission_service.is_authorized(user_id, UserRole.USER):
                return await func(update, context, *args, **kwargs)
            if await permission_service.can_generate_song(user_id):
                return await func(update, context, *args, **kwargs)
            if await permission_service.has_any_song_invitation(user_id):
                await update.message.reply_text(
                    "Has agotado tu cupo de canciones. Puedes solicitar más al administrador con /request_songs."
                )
                return ConversationHandler.END
        await update.message.reply_text(
            "Necesitas una invitación para usar este bot. Contacta al administrador."
        )
        return ConversationHandler.END
    return wrapped

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.core.config import settings

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    logger.info(f"Start command received from {user_id}: {text!r}")

    # Enlace de invitación cifrado: /start inv_<token> o /start inv_gate_<token>
    if text.startswith("/start "):
        from app.utils.invite_link import (
            INVITE_GATE_PREFIX,
            INVITE_PREFIX,
            decode_gate_payload,
            decode_invite_payload,
        )
        payload = text[7:].strip()
        secret = get_invite_link_secret()

        # Portón: inv_gate_<token>
        if payload.startswith(INVITE_GATE_PREFIX):
            token = payload[len(INVITE_GATE_PREFIX):].strip()
            data = decode_gate_payload(token, secret)
            if data and "d" in data:
                days = data["d"]
                user = update.effective_user
                async with AsyncSessionLocal() as session:
                    permission_service = PermissionService(session)
                    await permission_service.create_gate_invitation(
                        inviter_id=settings.ADMIN_TELEGRAM_ID,
                        invitee_id=user_id,
                        invitee_username=user.username or f"User_{user_id}",
                        days=days,
                        invitee_first_name=user.first_name,
                        invitee_last_name=user.last_name,
                    )
                from app.utils.user_display import format_user_display
                display = format_user_display(
                    first_name=user.first_name,
                    last_name=user.last_name,
                    username=user.username,
                    telegram_id=user_id,
                )
                msg_reply = (
                    f"✅ Tienes acceso al portón por {days} día(s).\n\n"
                    "Usa /gate_open cuando necesites abrir el portón. "
                    "No tienes acceso a otras funciones del bot (PC, canciones, etc.)."
                )
                reply_target = getattr(update, "message", None) or getattr(update, "effective_message", None)
                if reply_target:
                    await reply_target.reply_text(msg_reply)
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_reply)
                try:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_TELEGRAM_ID,
                        text=f"🚪 El usuario {display} ha usado tu enlace de portón y tiene {days} día(s) de acceso."
                    )
                except Exception as e:
                    logger.warning(f"Could not notify admin (gate link): {e}")
                return

        # Canciones: inv_<token>
        if payload.startswith(INVITE_PREFIX):
            token = payload[len(INVITE_PREFIX):].strip()
            data = decode_invite_payload(token, secret)
            if data and "c" in data:
                count = data["c"]
                user = update.effective_user
                async with AsyncSessionLocal() as session:
                    permission_service = PermissionService(session)
                    await permission_service.create_song_invitation(
                        inviter_id=settings.ADMIN_TELEGRAM_ID,
                        invitee_id=user_id,
                        invitee_username=user.username or f"User_{user_id}",
                        song_quota=count,
                        duration_hours=None,
                        invitee_first_name=user.first_name,
                        invitee_last_name=user.last_name,
                    )
                from app.utils.user_display import format_user_display
                display = format_user_display(
                    first_name=user.first_name,
                    last_name=user.last_name,
                    username=user.username,
                    telegram_id=user_id,
                )
                msg_reply = (
                    f"✅ Tienes {count} canción(es) de regalo.\n\n"
                    "*Qué puedes hacer:*\n"
                    "• /generate_song — Crear una canción.\n"
                    "• /request_songs — Pedir más canciones al administrador cuando se te acaben.\n\n"
                    "⚠️ El servicio de generación _puede no estar disponible en todo momento_. Si no funciona, contacta al administrador.\n\n"
                    "No tienes acceso a otras funciones del bot (PC, portón, etc.)."
                )
                reply_target = getattr(update, "message", None) or getattr(update, "effective_message", None)
                if reply_target:
                    await reply_target.reply_text(msg_reply, parse_mode="Markdown")
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_reply, parse_mode="Markdown")
                try:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_TELEGRAM_ID,
                        text=f"🎵 El usuario {display} ha usado tu enlace de invitación y tiene {count} canción(es)."
                    )
                except Exception as e:
                    logger.warning(f"Could not notify admin (invite link): {e}")
                return

    # Saludo según tipo de usuario (evitar confundir a invitados con mensaje de admin)
    async with AsyncSessionLocal() as session:
        permission_service = PermissionService(session)
        role = await permission_service.get_user_role(user_id)
        remaining = await permission_service.get_remaining_songs(user_id)
        bot_mode = getattr(settings, "BOT_MODE", "admin").strip().lower()

        # Bot de canciones: solo invitados (o admin) pueden usar el bot
        if bot_mode == "songs" and role != UserRole.ADMIN:
            if not await permission_service.has_any_song_invitation(user_id):
                await _reply_to_update(
                    update, context,
                    "Bienvenido al bot de canciones.\n\n"
                    "Este bot es solo para invitados. Necesitas un *enlace de invitación* del administrador para obtener cupo de canciones.\n\n"
                    f"Tu Telegram ID es: `{user_id}` (por si el administrador necesita invitarte).",
                    parse_mode="Markdown",
                )
                return

        # Bot de portón: solo invitados (o admin) pueden usar el bot
        if bot_mode == "gate" and role != UserRole.ADMIN:
            if not await permission_service.can_open_gate(user_id):
                await _reply_to_update(
                    update, context,
                    "Bienvenido al bot del portón.\n\n"
                    "Este bot es solo para invitados. Necesitas un *enlace de invitación* del administrador para el portón.\n\n"
                    f"Tu Telegram ID es: `{user_id}` (por si el administrador necesita invitarte).",
                    parse_mode="Markdown",
                )
                return

    if role == UserRole.ADMIN:
        await _reply_to_update(update, context,
            f"Bienvenido a RaspiHomeBot (administrador).\n\n"
            f"Tu Telegram ID es: `{user_id}`. Este ID debe estar en `ADMIN_TELEGRAM_ID` en el `.env`.\n\n"
            "Puedes usar todos los comandos del bot, invitar con /invite_link o /invite_songs y ver el estado con /invitations_status."
        )
    elif role == UserRole.USER:
        await _reply_to_update(update, context,
            "Bienvenido a RaspiHomeBot.\n\n"
            "Tienes acceso completo: encender/apagar PC, abrir portón, generar canciones, iniciar/parar ACE-Step y Ollama, etc. "
            "Usa el menú de comandos (/) para ver las opciones."
        )
    elif role == UserRole.GUEST and remaining is not None:
        await _reply_to_update(update, context,
            f"Bienvenido.\n\n"
            f"Eres un invitado con cupo de canciones. Te quedan *{remaining}* canción(es).\n\n"
            "*Qué puedes hacer:*\n"
            "• /generate_song — Crear una canción (usa tu cupo).\n"
            "• /request_songs — Pedir más canciones al administrador cuando se te acaben.\n\n"
            "⚠️ El servicio de generación _puede no estar disponible en todo momento_. Si no funciona, contacta al administrador.\n\n"
            "No tienes acceso a otras funciones del bot (PC, portón, etc.).",
            parse_mode="Markdown"
        )
    elif role == UserRole.GUEST:
        await _reply_to_update(update, context,
            "Bienvenido.\n\n"
            "Tenías un cupo de canciones pero ya lo has usado. Usa /request_songs para pedir más al administrador.\n\n"
            "No tienes acceso a otras funciones del bot."
        )
    else:
        await _reply_to_update(update, context,
            f"Bienvenido a RaspiHomeBot.\n\n"
            f"Tu Telegram ID es: `{user_id}` (por si el administrador necesita invitarte).\n\n"
            "Si te han enviado un *enlace de invitación*, ábrelo para obtener tu cupo de canciones. "
            "Si no, solo el administrador puede darte acceso.",
            parse_mode="Markdown"
        )

@restricted(UserRole.USER)
async def pc_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "pc_on", "source": f"chat_{update.effective_chat.id}"})
    else:
        # Fallback to direct call if bus not available (e.g. in tests)
        from app.services.wol_service import WOLService
        WOLService.send_wol()
        await update.message.reply_text("WOL packet sent. (Bus not found)")

@restricted(UserRole.USER)
async def pc_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "pc_off", "source": f"chat_{update.effective_chat.id}"})
    else:
        from app.services.wol_service import WOLService
        await WOLService.shutdown()
        await update.message.reply_text("Shutdown command sent. (Bus not found)")

@restricted(UserRole.USER)
async def pc_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "pc_status", "source": f"chat_{update.effective_chat.id}"})
    else:
        from app.services.wol_service import WOLService
        status = await WOLService.get_pc_status()
        await update.message.reply_text(f"PC Status: {status}")

@restricted(UserRole.USER)
async def status_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        # For summary, we might want to query the state store directly if possible, 
        # but for now we'll just trigger a status command.
        await bus.publish("command", {"command": "pc_status", "source": f"chat_{update.effective_chat.id}"})
        await bus.publish("command", {"command": "arlo_status", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("System status currently unavailable.")

def restricted_to_gate(func):
    """Permite USER, ADMIN o invitados con acceso al portón (gate)."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            if await permission_service.can_open_gate(user_id):
                return await func(update, context, *args, **kwargs)
        msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
        text = "Necesitas una invitación para usar este bot (portón). Contacta al administrador."
        if msg:
            await msg.reply_text(text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    return wrapped


@restricted_to_gate
async def gate_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.core.config import settings
    from app.services.gate_proxy_client import request_gate_open
    from app.services.usage_service import UsageService
    from app.utils.user_display import format_user_display

    user = update.effective_user
    user_id = user.id
    proxy_url = getattr(settings, "GATE_PROXY_URL", None) or None
    proxy_secret = getattr(settings, "GATE_PROXY_SECRET", None) or ""

    async with AsyncSessionLocal() as session:
        permission_service = PermissionService(session)
        role = await permission_service.get_user_role(user_id)
        gate_inv = await permission_service.get_gate_invitation(user_id)
        display = format_user_display(
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            telegram_id=user_id,
        )
        usage_service = UsageService(session)
        await usage_service.log_operation(
            user_id,
            "gate_opened",
            display_name=display,
        )

    # Si es invitado de portón y está configurado el proxy, enviar la orden al otro bot
    if role == UserRole.GUEST and gate_inv and proxy_url and proxy_secret:
        ok = await request_gate_open(
            proxy_url,
            proxy_secret,
            guest_telegram_id=user_id,
            admin_telegram_id=settings.ADMIN_TELEGRAM_ID,
        )
        reply = "Se ha enviado la orden de abrir el portón." if ok else "No se pudo contactar con el servicio del portón. Intenta más tarde."
        msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
        if msg:
            await msg.reply_text(reply)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=reply)
        return

    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "gate_open", "source": f"chat_{update.effective_chat.id}"})
    else:
        from app.services.gate_service import GateService
        await GateService.open_gate()
        msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
        if msg:
            await msg.reply_text("Opening gate... (Bus not found)")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Opening gate... (Bus not found)")


@restricted_to_gate
async def gate_entrada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía E (entrada) al canal PortonBot o usa proxy/bus si no hay canal configurado."""
    from app.core.config import settings
    from app.services.porton_channel_client import send_porton_command, get_porton_channel_id
    from app.services.usage_service import UsageService
    from app.utils.user_display import format_user_display

    user = update.effective_user
    user_id = user.id
    display = format_user_display(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        telegram_id=user_id,
    )
    async with AsyncSessionLocal() as session:
        usage_service = UsageService(session)
        await usage_service.log_operation(user_id, "gate_opened", display_name=display, metadata='{"action":"entrada"}')
    channel = get_porton_channel_id()
    if channel:
        ok = await send_porton_command(context.bot, "E")
        msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
        text = "Se ha enviado la orden de entrada (E) al portón. Si el otro bot responde, te lo haré saber cuando sea posible." if ok else "No se pudo enviar la orden al canal del portón. Intenta más tarde."
        if msg:
            await msg.reply_text(text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        return
    await gate_open(update, context)


@restricted_to_gate
async def gate_salida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía S (salida) al canal PortonBot o abre igual que gate_open si no hay canal."""
    from app.services.porton_channel_client import send_porton_command, get_porton_channel_id
    from app.services.usage_service import UsageService
    from app.utils.user_display import format_user_display

    user = update.effective_user
    user_id = user.id
    display = format_user_display(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        telegram_id=user_id,
    )
    async with AsyncSessionLocal() as session:
        usage_service = UsageService(session)
        await usage_service.log_operation(user_id, "gate_opened", display_name=display, metadata='{"action":"salida"}')
    channel = get_porton_channel_id()
    if channel:
        ok = await send_porton_command(context.bot, "S")
        msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
        text = "Se ha enviado la orden de salida (S) al portón. Si el otro bot responde, te lo haré saber cuando sea posible." if ok else "No se pudo enviar la orden al canal del portón. Intenta más tarde."
        if msg:
            await msg.reply_text(text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        return
    await gate_open(update, context)


@restricted(UserRole.ADMIN)
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Command: /invite <user_id> <hours>
    # Note: Telegram bot doesn't easily resolve @username to user_id unless the bot has seen the user.
    # For simplicity, we'll use user_id or expect the user to reply to a message from the person they want to invite.
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /invite <user_id> <hours>h")
        return

    try:
        invitee_id = int(args[0])
        duration_str = args[1].lower()
        if duration_str.endswith('h'):
            hours = int(duration_str[:-1])
        else:
            hours = int(duration_str)
            
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            await permission_service.create_invitation(
                inviter_id=update.effective_user.id,
                invitee_id=invitee_id,
                invitee_username=f"Guest_{invitee_id}", # Simplified
                duration_hours=hours
            )
        
        await update.message.reply_text(f"Access granted to user {invitee_id} for {hours} hours.")
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid arguments. Use: /invite <user_id> <hours>h")


async def _reply_to_update(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """Envía un mensaje al chat del update; evita fallar si update.message es None (p. ej. en canales)."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return
    msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if msg and hasattr(msg, "reply_text"):
        await msg.reply_text(text, **kwargs)
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)


@restricted(UserRole.ADMIN)
async def invite_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera un enlace de invitación cifrado; el bot te lo envía por mensaje privado. Uso: /invite_link <cantidad>"""
    from app.core.config import settings
    from app.utils.invite_link import INVITE_PREFIX, encode_invite_payload

    args = context.args
    if len(args) < 1:
        await _reply_to_update(update, context, "Uso: /invite_link <cantidad>\nEj: /invite_link 5 — te enviaré un enlace por privado; quien lo abra tendrá esa cantidad de canciones.")
        return
    try:
        count = int(args[0])
        if count < 1 or count > 999:
            await _reply_to_update(update, context, "La cantidad debe estar entre 1 y 999.")
            return
    except ValueError:
        await _reply_to_update(update, context, "Indica un número válido de canciones.")
        return
    secret = get_invite_link_secret()
    token = encode_invite_payload(count, secret)
    if not token:
        await _reply_to_update(update, context, "Error al generar el enlace (falta instalar 'cryptography').")
        return
    bot_username = getattr(settings, "SONGS_BOT_USERNAME", None) or None
    if not bot_username:
        me = await context.bot.get_me()
        bot_username = me.username if me else None
    if not bot_username:
        await _reply_to_update(update, context, "No se pudo obtener el nombre del bot de canciones (configura SONGS_BOT_USERNAME o usa este bot).")
        return
    link = f"https://t.me/{bot_username}?start={INVITE_PREFIX}{token}"
    admin_chat_id = update.effective_user.id
    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"🔗 Enlace de invitación ({count} canción/canciones):\n\n{link}\n\nEnvía este enlace a la persona que quieres invitar. Al abrirlo tendrá {count} canciones para generar."
        )
        if update.effective_chat.id != admin_chat_id:
            await _reply_to_update(update, context, "Te he enviado el enlace por mensaje privado.")
        else:
            await _reply_to_update(update, context, f"Enlace generado ({count} canciones). Revisa el mensaje de arriba.")
    except Exception as e:
        logger.warning(f"Could not send invite link to admin: {e}")
        await _reply_to_update(update, context, "No pude enviarte el enlace por privado. Asegúrate de haber iniciado chat con el bot y vuelve a intentar.")


@restricted(UserRole.ADMIN)
async def invite_link_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera un enlace de invitación al portón (días); el bot te lo envía por mensaje privado. Uso: /gate_invite_link <días>"""
    from app.core.config import settings
    from app.utils.invite_link import INVITE_GATE_PREFIX, encode_gate_payload

    args = context.args
    if len(args) < 1:
        await _reply_to_update(update, context, "Uso: /gate_invite_link <días>\nEj: /gate_invite_link 7 — te enviaré un enlace por privado; quien lo abra tendrá acceso al portón esos días.")
        return
    try:
        days = int(args[0])
        if days < 1 or days > 3650:
            await _reply_to_update(update, context, "Los días deben estar entre 1 y 3650.")
            return
    except ValueError:
        await _reply_to_update(update, context, "Indica un número válido de días.")
        return
    secret = get_invite_link_secret()
    token = encode_gate_payload(days, secret)
    if not token:
        await _reply_to_update(update, context, "Error al generar el enlace (falta instalar 'cryptography').")
        return
    bot_username = getattr(settings, "GATE_BOT_USERNAME", None) or None
    if not bot_username:
        me = await context.bot.get_me()
        bot_username = me.username if me else None
    if not bot_username:
        await _reply_to_update(update, context, "No se pudo obtener el nombre del bot de portón (configura GATE_BOT_USERNAME o usa este bot).")
        return
    link = f"https://t.me/{bot_username}?start={INVITE_GATE_PREFIX}{token}"
    admin_chat_id = update.effective_user.id
    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"🔗 Enlace de invitación al portón ({days} día(s)):\n\n{link}\n\nEnvía este enlace a la persona. Al abrirlo tendrá acceso a /gate_open durante {days} día(s)."
        )
        if update.effective_chat.id != admin_chat_id:
            await _reply_to_update(update, context, "Te he enviado el enlace por mensaje privado.")
        else:
            await _reply_to_update(update, context, f"Enlace generado ({days} días). Revisa el mensaje de arriba.")
    except Exception as e:
        logger.warning(f"Could not send gate invite link to admin: {e}")
        await _reply_to_update(update, context, "No pude enviarte el enlace por privado. Asegúrate de haber iniciado chat con el bot y vuelve a intentar.")


@restricted(UserRole.ADMIN)
async def invite_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invitación al portón por user_id y días: /gate_invite <user_id> <días>"""
    args = context.args
    if len(args) < 2:
        await _reply_to_update(update, context, "Uso: /gate_invite <user_id> <días>\nEj: /gate_invite 123456 7")
        return
    try:
        invitee_id = int(args[0])
        days = int(args[1])
        if days < 1 or days > 3650:
            await _reply_to_update(update, context, "Los días deben estar entre 1 y 3650.")
            return
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            await permission_service.create_gate_invitation(
                inviter_id=update.effective_user.id,
                invitee_id=invitee_id,
                invitee_username=f"Guest_{invitee_id}",
                days=days,
            )
        await _reply_to_update(update, context, f"Invitación al portón creada: usuario {invitee_id} tiene acceso durante {days} día(s).")
    except (ValueError, IndexError):
        await _reply_to_update(update, context, "Argumentos inválidos. Uso: /gate_invite <user_id> <días>")


@restricted(UserRole.ADMIN)
async def invite_songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invitación para generar solo canciones: /invite_songs <user_id> <cantidad> [horas]"""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Uso: /invite_songs <user_id> <cantidad> [horas]\nEj: /invite_songs 123456 5   o  /invite_songs 123456 5 720h")
        return
    try:
        invitee_id = int(args[0])
        count = int(args[1])
        if count < 1:
            await update.message.reply_text("La cantidad debe ser al menos 1.")
            return
        hours = None
        if len(args) >= 3:
            s = args[2].lower()
            if s.endswith("h"):
                hours = int(s[:-1])
            else:
                hours = int(s)
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            await permission_service.create_song_invitation(
                inviter_id=update.effective_user.id,
                invitee_id=invitee_id,
                invitee_username=f"Guest_{invitee_id}",
                song_quota=count,
                duration_hours=hours,
            )
        msg = f"Invitación de canciones creada: usuario {invitee_id} puede generar {count} canción(es)."
        if hours:
            msg += f" Válida {hours} horas."
        await update.message.reply_text(msg)
    except (ValueError, IndexError):
        await update.message.reply_text("Argumentos inválidos. Uso: /invite_songs <user_id> <cantidad> [horas]")


async def solicitar_canciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """El invitado solicita más cupo de canciones; se registra AccessRequest y se notifica al admin."""
    from app.core.config import settings
    from app.services.usage_service import UsageService
    from app.utils.user_display import format_user_display

    user = update.effective_user
    user_id = user.id
    display = format_user_display(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        telegram_id=user_id,
    )
    async with AsyncSessionLocal() as session:
        permission_service = PermissionService(session)
        if not await permission_service.has_any_song_invitation(user_id):
            await _reply_to_update(update, context, "Necesitas una invitación para usar este bot. Contacta al administrador.")
            return
        usage_service = UsageService(session)
        await usage_service.create_access_request(user_id, "more_songs", requested_value="+N")
    await _reply_to_update(update, context, "Se ha notificado al administrador. Cuando te autorice más canciones podrás seguir generando.")
    try:
        await context.bot.send_message(
            chat_id=settings.ADMIN_TELEGRAM_ID,
            text=f"🎵 Solicitud de más canciones: {display}. "
            "Para darle más cupo: /grant_songs <user_id> <cantidad>\nEj: /grant_songs " + str(user_id) + " 5"
        )
    except Exception as e:
        logger.warning(f"Could not notify admin: {e}")


@restricted(UserRole.ADMIN)
async def grant_songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Añade cupo de canciones a un usuario y resuelve solicitud pendiente si existe."""
    from app.services.usage_service import UsageService
    from app.database.models import AccessRequestStatus

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Uso: /grant_songs <user_id> <cantidad>\nEj: /grant_songs 123456 5")
        return
    try:
        invitee_id = int(args[0])
        count = int(args[1])
        if count < 1:
            await update.message.reply_text("La cantidad debe ser al menos 1.")
            return
        admin_id = update.effective_user.id
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            await permission_service.add_song_quota(
                admin_id=admin_id,
                invitee_telegram_id=invitee_id,
                count=count,
                invitee_username=None,
            )
            usage_service = UsageService(session)
            pending = await usage_service.list_access_requests(status=AccessRequestStatus.PENDING.value, telegram_id=invitee_id, limit=1)
            if pending:
                await usage_service.resolve_access_request(
                    pending[0].id,
                    AccessRequestStatus.APPROVED.value,
                    responded_by=admin_id,
                    notes=f"+{count} canciones",
                )
        await update.message.reply_text(f"Se han añadido {count} canciones al usuario {invitee_id}.")
    except (ValueError, IndexError):
        await update.message.reply_text("Argumentos inválidos. Uso: /grant_songs <user_id> <cantidad>")


@restricted(UserRole.ADMIN)
async def estado_invitaciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista estado de invitaciones por cupo de canciones: generadas, restantes, expiración."""
    async with AsyncSessionLocal() as session:
        permission_service = PermissionService(session)
        rows = await permission_service.list_song_invitations()
    if not rows:
        await _reply_to_update(update, context, "No hay invitaciones activas por cupo de canciones.")
        return
    lines = ["📋 *Estado de invitaciones (canciones)*\n"]
    for r in rows:
        exp = r["expiration_time"].strftime("%Y-%m-%d %H:%M") if hasattr(r["expiration_time"], "strftime") else str(r["expiration_time"])
        first = ""
        if r.get("first_used_at"):
            first = f" · Primera vez: {r['first_used_at'].strftime('%Y-%m-%d %H:%M')}" if hasattr(r["first_used_at"], "strftime") else ""
        display = r.get("display_name") or r.get("invitee_username") or f"ID {r['invitee_telegram_id']}"
        lines.append(
            f"• {display}\n"
            f"  Generadas: {r['songs_used']}/{r['song_quota']} · Quedan: {r['remaining']} · Expira: {exp}{first}"
        )
    await _reply_to_update(update, context, "\n".join(lines), parse_mode="Markdown")


@restricted(UserRole.USER)
async def acestep_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await update.message.reply_text("Intentando iniciar la API de ACE-Step...")
        await bus.publish("command", {"command": "acestep_start", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def acestep_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await update.message.reply_text("Intentando detener la API de ACE-Step...")
        await bus.publish("command", {"command": "acestep_stop", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def acestep_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "acestep_save", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus no disponible.")

@restricted(UserRole.USER)
async def ollama_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await update.message.reply_text("Intentando iniciar Ollama...")
        await bus.publish("command", {"command": "ollama_start", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def ollama_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await update.message.reply_text("Intentando detener Ollama...")
        await bus.publish("command", {"command": "ollama_stop", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted_to_song
async def generate_song_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.core.config import settings
    from app.services.acestep_service import AceStepService

    user_id = update.effective_user.id
    username = (update.effective_user.username or "") and f"@{update.effective_user.username}" or str(user_id)

    async with AsyncSessionLocal() as session:
        permission_service = PermissionService(session)
        role = await permission_service.get_user_role(user_id)
    is_song_guest = role == UserRole.GUEST

    if is_song_guest:
        from app.utils.user_display import format_user_display
        display = format_user_display(
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
            username=update.effective_user.username,
            telegram_id=user_id,
        )
        async with AsyncSessionLocal() as session:
            perm2 = PermissionService(session)
            if await perm2.mark_invitation_first_used(user_id):
                try:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_TELEGRAM_ID,
                        text=f"🎵 {display} ha empezado a usar su invitación por primera vez (aceptación)."
                    )
                except Exception as e:
                    logger.warning(f"Could not notify admin (first use): {e}")
        api_ready = await AceStepService.is_api_ready()
        if not api_ready:
            await update.message.reply_text(
                "En este momento el servicio de generación no está disponible. "
                "Si el problema continúa, contacta al administrador. Se le ha notificado."
            )
            from app.utils.user_display import format_user_display
            display = format_user_display(
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name,
                username=update.effective_user.username,
                telegram_id=user_id,
            )
            try:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_TELEGRAM_ID,
                    text=f"🎵 {display} quiere generar una canción pero el servicio no está activo. "
                    "Puedes iniciarlo con /acestep_start y, si usan IA, /ollama_start."
                )
            except Exception as e:
                logger.warning(f"Could not notify admin: {e}")
            return ConversationHandler.END

    # Limpiar estado de intentos anteriores
    for key in ("song_style", "song_lyrics", "refine_target", "style_only", "song_theme", "song_lyrics_lang"):
        context.user_data.pop(key, None)
    reply_keyboard = [["Manual", "Asistido por IA"]]
    await update.message.reply_text(
        "¡Genial! Vamos a crear una canción. ¿Cómo quieres proceder?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return MODE_SELECT

async def generate_song_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text.lower()
    if "ia" in mode:
        if not await OllamaService.is_available():
            await update.message.reply_text(
                "Ollama no está activo. Intentando iniciarlo… (puede tardar unos segundos)."
            )
            success, error_msg = await OllamaService.start_ollama()
            if success and await OllamaService.is_available():
                await update.message.reply_text("✅ Ollama listo. Continuamos con asistencia por IA.")
            else:
                await update.message.reply_text(
                    "No se pudo iniciar Ollama. Continuamos en modo manual. "
                    "Puedes usar /ollama_start más tarde e intentar de nuevo."
                    + (f"\n\n{error_msg}" if error_msg else "")
                )
                return await generate_song_ask_style(update, context)

        # Preguntar si con letra o solo estilo (instrumental); si solo estilo no preguntamos idioma
        reply_keyboard = [["Con letra", "Solo estilo (sin letra)"]]
        await update.message.reply_text(
            "¿La canción llevará letra o solo quieres definir el estilo (instrumental)?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return LYRICS_OR_STYLE
    else:
        return await generate_song_ask_style(update, context)


async def generate_song_lyrics_or_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "solo" in text or "estilo" in text or "instrumental" in text or "sin letra" in text:
        context.user_data["style_only"] = True
        await update.message.reply_text(
            "Describe el tema o estilo musical que quieres (ej: rock épico, ambiente cinematográfico). "
            "El agente generará los tags del estilo en inglés para ACE-Step.",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        context.user_data["style_only"] = False
        await update.message.reply_text(
            "Describe el tema de la canción, sentimientos o lo que quieras para que la IA genere estilo y letra. "
            "Luego elegirás en qué idioma quieres la letra.",
            reply_markup=ReplyKeyboardRemove()
        )
    return AI_PROMPT

async def generate_song_ask_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¿Cuál es el estilo o descripción de la música que quieres?",
        reply_markup=ReplyKeyboardRemove()
    )
    return STYLE

def _build_language_keyboard():
    from app.prompts import LYRICS_LANGUAGE_OPTIONS
    buttons = [
        [InlineKeyboardButton(name, callback_data=f"lang_{code}")]
        for code, name in LYRICS_LANGUAGE_OPTIONS
    ]
    return InlineKeyboardMarkup(buttons)


async def _send_suggestion_and_review(update_or_query, context: ContextTypes.DEFAULT_TYPE, suggestions: dict, is_style_only: bool):
    """Envía la sugerencia de estilo/letra y muestra botones de revisión. update_or_query es update o callback_query (con .message)."""
    context.user_data["song_style"] = suggestions["style"]
    context.user_data["song_lyrics"] = suggestions.get("lyrics") or ""
    lyrics_display = (suggestions.get("lyrics") or "").strip() or "(Solo estilo / sin letra)"
    response_text = (
        f"🤖 *Sugerencia de la IA:*\n\n"
        f"*Estilo:* {suggestions['style']}\n\n"
        f"*Letra:*\n{lyrics_display}\n\n"
        "¿Qué te parece?"
    )
    reply_keyboard = [["Aceptar", "Refinar estilo", "Refinar letra", "Regenerar todo"]]
    if is_style_only:
        reply_keyboard = [["Aceptar", "Refinar estilo", "Regenerar todo"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    msg = update_or_query.message
    await msg.reply_text(response_text, parse_mode="Markdown", reply_markup=markup)


async def generate_song_ai_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text.strip()
    is_refinement = "refine_target" in context.user_data
    style_only = context.user_data.get("style_only", False)
    theme = context.user_data.get("song_theme") if is_refinement else user_prompt
    if not is_refinement:
        context.user_data["song_theme"] = user_prompt

    if is_refinement:
        await update.message.reply_text("Aplicando cambios... Por favor espera.")
        refinamiento = user_prompt
        suggestions = await OllamaService.suggest_song_details(
            theme,
            refinamiento=refinamiento,
            language_code=context.user_data.get("song_lyrics_lang"),
            style_only=style_only,
        )
        if not suggestions:
            await update.message.reply_text("No se pudo aplicar el refinamiento. Intenta de nuevo:")
            return AI_PROMPT
        if suggestions.get("error") == "model_not_found":
            msg = suggestions.get("message", "El modelo configurado no está instalado en Ollama.")
            await update.message.reply_text(f"❌ {msg}\n\nPuedes usar /generate_song y elegir **Manual**.", parse_mode="Markdown")
            return ConversationHandler.END
        context.user_data.pop("refine_target", None)
        await _send_suggestion_and_review(update, context, suggestions, style_only)
        return AI_REVIEW

    await update.message.reply_text("Generando sugerencias con Ollama... Por favor espera.")
    if style_only:
        suggestions = await OllamaService.suggest_song_details(theme, style_only=True)
        if not suggestions:
            await update.message.reply_text("Hubo un error al generar. Intenta describir el tema de nuevo:")
            return AI_PROMPT
        if suggestions.get("error") == "model_not_found":
            msg = suggestions.get("message", "El modelo configurado no está instalado en Ollama.")
            await update.message.reply_text(f"❌ {msg}\n\nPuedes usar /generate_song y elegir **Manual**.", parse_mode="Markdown")
            return ConversationHandler.END
        await _send_suggestion_and_review(update, context, suggestions, style_only=True)
        return AI_REVIEW

    # Con letra: pedir idioma con InlineKeyboard
    await update.message.reply_text(
        "¿En qué idioma quieres la letra? (El estilo se genera siempre en inglés para el modelo.)",
        reply_markup=_build_language_keyboard()
    )
    return AI_LANGUAGE


async def generate_song_ask_language_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recuerda al usuario que use los botones para elegir idioma."""
    await update.message.reply_text(
        "Elige el idioma de la letra con los botones de abajo.",
        reply_markup=_build_language_keyboard()
    )
    return AI_LANGUAGE


async def generate_song_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.startswith("lang_"):
        return AI_LANGUAGE
    code = query.data.replace("lang_", "", 1)
    context.user_data["song_lyrics_lang"] = code
    theme = context.user_data.get("song_theme", "")
    await query.message.reply_text("Generando sugerencias con Ollama... Por favor espera.")
    suggestions = await OllamaService.suggest_song_details(theme, language_code=code)
    if not suggestions:
        await query.message.reply_text("Error al generar. Intenta de nuevo con /generate_song.")
        return ConversationHandler.END
    if suggestions.get("error") == "model_not_found":
        msg = suggestions.get("message", "El modelo no está instalado en Ollama.")
        await query.message.reply_text(f"❌ {msg}", parse_mode="Markdown")
        return ConversationHandler.END
    await _send_suggestion_and_review(query, context, suggestions, is_style_only=False)
    return AI_REVIEW

async def generate_song_ai_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.lower()
    
    if "aceptar" in choice:
        return await generate_song_finish(update, context, context.user_data.get("song_lyrics", ""))
    
    elif "estilo" in choice:
        await update.message.reply_text("Dime qué cambios quieres en el estilo:")
        context.user_data["refine_target"] = "style"
        return AI_PROMPT
        
    elif "letra" in choice:
        await update.message.reply_text("Dime qué cambios quieres en la letra:")
        context.user_data["refine_target"] = "lyrics"
        return AI_PROMPT
        
    elif "regenerar" in choice:
        await update.message.reply_text("Entendido. Dame nuevas indicaciones o describe mejor lo que buscas:")
        context.user_data.pop("refine_target", None)
        return AI_PROMPT
    
    else:
        await update.message.reply_text("No entendí esa opción. Por favor usa los botones.")
        return AI_REVIEW

async def generate_song_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["song_style"] = update.message.text
    reply_keyboard = [["Sí", "No"]]
    await update.message.reply_text(
        f"Estilo: {update.message.text}\n¿Quieres añadir letra personalizada?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return LYRICS_CHOICE

async def generate_song_lyrics_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.lower()
    if choice == "sí":
        await update.message.reply_text("Por favor, envía la letra de la canción:", reply_markup=ReplyKeyboardRemove())
        return LYRICS_TEXT
    else:
        # Proceed to generation
        return await generate_song_finish(update, context, "")

async def generate_song_lyrics_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lyrics = update.message.text
    return await generate_song_finish(update, context, lyrics)

async def generate_song_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, lyrics: str):
    style = context.user_data.get("song_style") or ""
    style = (style or "").strip()
    bus = context.bot_data.get("bus")

    if not style:
        await update.message.reply_text(
            "No se encontró el estilo de la canción. Por favor usa /generate_song de nuevo y elige Manual o Asistido por IA.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Iniciando generación... Esto puede tardar unos minutos.\n"
        "Si te gusta el resultado, podrás guardarla permanentemente con /save_song.",
        reply_markup=ReplyKeyboardRemove()
    )

    if bus:
        user_id = update.effective_user.id
        username = (update.effective_user.username or "") and f"@{update.effective_user.username}" or str(user_id)
        from app.utils.user_display import format_user_display
        display = format_user_display(
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
            username=update.effective_user.username,
            telegram_id=user_id,
        )
        await bus.publish("command", {
            "command": "acestep_generate",
            "source": f"chat_{update.effective_chat.id}",
            "prompt": style,
            "lyrics": lyrics or "",
            "user_id": user_id,
            "username": username,
            "display_name": display,
        })
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            if await permission_service.get_user_role(user_id) == UserRole.GUEST:
                if await permission_service.consume_song_quota(user_id):
                    from app.services.usage_service import UsageService
                    usage_service = UsageService(session)
                    await usage_service.log_operation(
                        user_id,
                        "song_generated",
                        display_name=display,
                    )
                    remaining = await permission_service.get_remaining_songs(user_id)
                    if remaining is not None:
                        await update.message.reply_text(f"Te quedan {remaining} canciones en tu cupo.")
    else:
        await update.message.reply_text("Error: Event bus no disponible.")

    return ConversationHandler.END

async def generate_song_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def save_admin_song_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Al pulsar 'Guardar en servidor' en la copia de canción enviada al admin."""
    from app.core.config import settings
    if update.callback_query.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await update.callback_query.answer("Solo el administrador puede guardar.", show_alert=True)
        return
    await update.callback_query.answer("Guardando en servidor...")
    bus = context.bot_data.get("bus")
    if not bus:
        await update.callback_query.message.reply_text("Error: bus no disponible.")
        return
    await bus.publish("command", {"command": "acestep_save", "source": f"chat_{settings.ADMIN_TELEGRAM_ID}"})
