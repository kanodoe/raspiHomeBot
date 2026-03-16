from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

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
                    await update.message.reply_text("You are not authorized to use this command.")
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
                    "Has agotado tu cupo de canciones. Puedes solicitar más al administrador con /solicitar_canciones."
                )
                return ConversationHandler.END
        await update.message.reply_text("No tienes permiso para generar canciones.")
        return ConversationHandler.END
    return wrapped

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Start command received from {user_id}")
    await update.message.reply_text(
        f"Bienvenido a RaspiHomeBot.\nTu Telegram ID es: `{user_id}`\n"
        f"Asegúrate de que este ID esté configurado como `ADMIN_TELEGRAM_ID` en tu archivo `.env`."
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

@restricted(UserRole.GUEST)
async def gate_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "gate_open", "source": f"chat_{update.effective_chat.id}"})
    else:
        from app.services.gate_service import GateService
        await GateService.open_gate()
        await update.message.reply_text("Opening gate... (Bus not found)")

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
    """El invitado solicita más cupo de canciones; se notifica al admin."""
    from app.core.config import settings
    user_id = update.effective_user.id
    username = (update.effective_user.username or "") and f"@{update.effective_user.username}" or str(user_id)
    async with AsyncSessionLocal() as session:
        permission_service = PermissionService(session)
        if not await permission_service.has_any_song_invitation(user_id):
            await update.message.reply_text("Solo los invitados con cupo de canciones pueden usar este comando para solicitar más.")
            return
    await update.message.reply_text(
        "Se ha notificado al administrador. Cuando te autorice más canciones podrás seguir generando."
    )
    try:
        await context.bot.send_message(
            chat_id=settings.ADMIN_TELEGRAM_ID,
            text=f"🎵 Solicitud de más canciones: {username} (ID: {user_id}). "
            "Para darle más cupo: /grant_songs <user_id> <cantidad>\nEj: /grant_songs " + str(user_id) + " 5"
        )
    except Exception as e:
        logger.warning(f"Could not notify admin: {e}")


@restricted(UserRole.ADMIN)
async def grant_songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Añade cupo de canciones a un usuario: /grant_songs <user_id> <cantidad>"""
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
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            await permission_service.add_song_quota(
                admin_id=update.effective_user.id,
                invitee_telegram_id=invitee_id,
                count=count,
                invitee_username=None,
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
        await update.message.reply_text("No hay invitaciones activas por cupo de canciones.")
        return
    from datetime import datetime as dt
    lines = ["📋 *Estado de invitaciones (canciones)*\n"]
    for r in rows:
        exp = r["expiration_time"].strftime("%Y-%m-%d %H:%M") if hasattr(r["expiration_time"], "strftime") else str(r["expiration_time"])
        first = ""
        if r.get("first_used_at"):
            first = f" · Primera vez: {r['first_used_at'].strftime('%Y-%m-%d %H:%M')}" if hasattr(r["first_used_at"], "strftime") else ""
        lines.append(
            f"• {r['invitee_username']} (ID: {r['invitee_telegram_id']})\n"
            f"  Generadas: {r['songs_used']}/{r['song_quota']} · Quedan: {r['remaining']} · Expira: {exp}{first}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
        async with AsyncSessionLocal() as session:
            perm2 = PermissionService(session)
            if await perm2.mark_invitation_first_used(user_id):
                try:
                    await context.bot.send_message(
                        chat_id=settings.ADMIN_TELEGRAM_ID,
                        text=f"🎵 El usuario {username} (ID: {user_id}) ha empezado a usar su invitación por primera vez (aceptación)."
                    )
                except Exception as e:
                    logger.warning(f"Could not notify admin (first use): {e}")
        api_ready = await AceStepService.is_api_ready()
        if not api_ready:
            await update.message.reply_text(
                "En este momento el servicio de generación no está disponible. "
                "Debes esperar a que se inicie; se ha notificado al administrador."
            )
            try:
                await context.bot.send_message(
                    chat_id=settings.ADMIN_TELEGRAM_ID,
                    text=f"🎵 El usuario {username} (ID: {user_id}) quiere generar una canción pero el servicio no está activo. "
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
        await bus.publish("command", {
            "command": "acestep_generate",
            "source": f"chat_{update.effective_chat.id}",
            "prompt": style,
            "lyrics": lyrics or "",
            "user_id": user_id,
            "username": username,
        })
        async with AsyncSessionLocal() as session:
            permission_service = PermissionService(session)
            if await permission_service.get_user_role(user_id) == UserRole.GUEST:
                if await permission_service.consume_song_quota(user_id):
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
