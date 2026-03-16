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
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ConversationHandler, MessageHandler, filters

# Conversation states for generate_song
MODE_SELECT, STYLE, LYRICS_CHOICE, LYRICS_TEXT, AI_PROMPT, AI_REVIEW = range(6)

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

@restricted(UserRole.USER)
async def acestep_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "acestep_start", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def acestep_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "acestep_stop", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def ollama_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "ollama_start", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def ollama_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "ollama_stop", "source": f"chat_{update.effective_chat.id}"})
    else:
        await update.message.reply_text("Event bus not available.")

@restricted(UserRole.USER)
async def generate_song_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await update.message.reply_text("Lo siento, el servicio de IA (Ollama) no está disponible en este momento. Usaremos el modo manual.")
            return await generate_song_ask_style(update, context)
        
        await update.message.reply_text(
            "Describe el tema de la canción, sentimientos o cualquier indicación para que la IA genere opciones:",
            reply_markup=ReplyKeyboardRemove()
        )
        return AI_PROMPT
    else:
        return await generate_song_ask_style(update, context)

async def generate_song_ask_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¿Cuál es el estilo o descripción de la música que quieres?",
        reply_markup=ReplyKeyboardRemove()
    )
    return STYLE

async def generate_song_ai_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    await update.message.reply_text("Generando sugerencias con Ollama... Por favor espera.")
    
    suggestions = await OllamaService.suggest_song_details(user_prompt)
    if not suggestions:
        await update.message.reply_text("Hubo un error al generar sugerencias. Por favor, intenta describir el tema de nuevo:")
        return AI_PROMPT
    
    context.user_data["song_style"] = suggestions["style"]
    context.user_data["song_lyrics"] = suggestions["lyrics"]
    
    response_text = (
        f"🤖 *Sugerencia de la IA:*\n\n"
        f"*Estilo:* {suggestions['style']}\n\n"
        f"*Letra:*\n{suggestions['lyrics']}\n\n"
        "¿Qué te parece?"
    )
    
    reply_keyboard = [["Aceptar", "Refinar estilo", "Refinar letra", "Regenerar todo"]]
    await update.message.reply_text(
        response_text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
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
    style = context.user_data.get("song_style")
    bus = context.bot_data.get("bus")
    
    await update.message.reply_text("Iniciando generación... Esto puede tardar unos minutos.", reply_markup=ReplyKeyboardRemove())
    
    if bus:
        await bus.publish("command", {
            "command": "acestep_generate", 
            "source": f"chat_{update.effective_chat.id}",
            "prompt": style,
            "lyrics": lyrics
        })
    else:
        await update.message.reply_text("Error: Event bus no disponible.")
    
    return ConversationHandler.END

async def generate_song_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
