import sys
import uvicorn
import gc
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler
from telegram.error import InvalidToken

from app.core.config import settings
from app.core.logging import logger
from app.core.event_bus import EventBus
from app.api.routes import router as api_router
from app.api.db_routes import router as db_router
from app.database.session import init_db, AsyncSessionLocal
from app.services.permission_service import PermissionService
from app.bot.handlers import (
    pc_on, pc_off, pc_status, status_summary, gate_open, gate_entrada, gate_salida, invite, start,
    invite_link, invite_link_gate, invite_gate, invite_songs, solicitar_canciones, grant_songs, estado_invitaciones,
    save_admin_song_callback,
    acestep_start, acestep_stop, acestep_save, ollama_start, ollama_stop,
    generate_song_start, generate_song_mode, generate_song_style,
    generate_song_lyrics_choice, generate_song_lyrics_text,
    generate_song_lyrics_or_style, generate_song_ai_prompt, generate_song_ai_review,
    generate_song_language_callback, generate_song_ask_language_buttons, generate_song_cancel,
    MODE_SELECT, STYLE, LYRICS_CHOICE, LYRICS_TEXT, AI_PROMPT, AI_REVIEW,
    LYRICS_OR_STYLE, AI_LANGUAGE,
)
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters

# Modules
from app.modules.command_router import CommandRouter
from app.modules.zigbee_adapter import ZigbeeAdapter
from app.modules.arlo_adapter import ArloAdapter
from app.modules.scheduler import SchedulerModule
from app.modules.notifier import Notifier
from app.modules.state_store import StateStore
from app.modules.pc_controller import PCController
from app.modules.gate_controller import GateController
from app.modules.permission_controller import PermissionController
from app.modules.acestep_controller import AceStepController

# Telegram Bot Setup
def get_enabled_modules():
    return [m.strip().lower() for m in settings.ENABLED_MODULES.split(",")]

def get_bot_mode():
    return (getattr(settings, "BOT_MODE", None) or "admin").strip().lower()

async def register_commands(bot):
    enabled = get_enabled_modules()
    mode = get_bot_mode()
    commands = [BotCommand("start", "Ver mi ID y estado del bot")]
    if mode == "admin":
        if "pc" in enabled:
            commands.extend([
                BotCommand("pc_on", "Encender PC (WOL)"),
                BotCommand("pc_off", "Apagar PC (SSH)"),
                BotCommand("pc_status", "Estado de red del PC"),
            ])
        if "gate" in enabled:
            commands.append(BotCommand("gate_open", "Abrir el portón (Invitados)"))
            commands.append(BotCommand("entrada", "Entrada (portón)"))
            commands.append(BotCommand("salida", "Salida (portón)"))
            commands.append(BotCommand("invite", "Invitar usuario (Admin)"))
            commands.append(BotCommand("gate_invite_link", "Enlace invitación portón (Admin)"))
            commands.append(BotCommand("gate_invite", "Invitación portón por user_id (Admin)"))
        commands.append(BotCommand("status", "Resumen del sistema"))
        if "acestep" in enabled:
            commands.extend([
                BotCommand("acestep_start", "Iniciar ACE-Step API"),
                BotCommand("acestep_stop", "Detener ACE-Step API"),
                BotCommand("save_song", "Guardar permanentemente la última canción"),
            ])
        if "ollama" in enabled:
            commands.extend([
                BotCommand("ollama_start", "Iniciar Ollama"),
                BotCommand("ollama_stop", "Detener Ollama"),
            ])
        if "acestep" in enabled:
            commands.append(BotCommand("generate_song", "Generar una canción (AI)"))
            commands.append(BotCommand("invite_link", "Generar enlace de invitación (Admin)"))
            commands.append(BotCommand("invite_songs", "Invitación por cupo de canciones (Admin)"))
            commands.append(BotCommand("grant_songs", "Dar más canciones a un usuario (Admin)"))
            commands.append(BotCommand("request_songs", "Solicitar más cupo al administrador"))
            commands.append(BotCommand("invitations_status", "Ver estado de invitaciones (Admin)"))
    elif mode == "songs":
        commands.append(BotCommand("generate_song", "Generar una canción (AI)"))
        commands.append(BotCommand("request_songs", "Solicitar más cupo al administrador"))
    elif mode == "gate":
        commands.append(BotCommand("gate_open", "Abrir el portón"))
        commands.append(BotCommand("entrada", "Entrada (portón)"))
        commands.append(BotCommand("salida", "Salida (portón)"))
    await bot.set_my_commands(commands)
    logger.info("Telegram bot commands registered in API.")

# Descripción y mensaje corto del bot por modo (lo que ve el usuario al abrir el chat o al compartir el bot)
BOT_DESCRIPTIONS = {
    "admin": (
        "Bot de administración del hogar: encender/apagar PC, abrir portón, gestionar invitaciones y generar canciones con IA.",
        "Administración: PC, portón, invitaciones y canciones.",
    ),
    "songs": (
        "Genera canciones con IA. Necesitas un enlace de invitación del administrador para obtener cupo. Si el servicio no está disponible, contacta al admin.",
        "Genera canciones con IA. Necesitas invitación del admin.",
    ),
    "gate": (
        "Abrir el portón y registrar entrada/salida. Necesitas un enlace de invitación del administrador para usar el bot.",
        "Abrir portón y registrar entrada/salida. Invitación del admin.",
    ),
}

async def set_bot_descriptions(bot):
    """Configura la descripción y short description del bot según BOT_MODE."""
    mode = get_bot_mode()
    desc, short = BOT_DESCRIPTIONS.get(mode, BOT_DESCRIPTIONS["admin"])
    try:
        await bot.set_my_description(desc)
        await bot.set_my_short_description(short[:120] if short else "")
        logger.info("Telegram bot description and short description set for mode=%s.", mode)
    except Exception as e:
        logger.warning("Could not set bot description/short_description: %s", e)

async def _post_init(application):
    """Se ejecuta tras initialize() para cada proceso (admin, songs, gate). Registra comandos y descripción."""
    await register_commands(application.bot)
    await set_bot_descriptions(application.bot)

def setup_bot():
    from app.core.config import get_bot_token_for_mode
    enabled = get_enabled_modules()
    mode = get_bot_mode()
    token = get_bot_token_for_mode(mode)
    application = ApplicationBuilder().token(token).post_init(_post_init).build()

    application.add_handler(CommandHandler("start", start))

    if mode == "admin":
        application.add_handler(CommandHandler("status", status_summary))
        if "pc" in enabled:
            application.add_handler(CommandHandler("pc_on", pc_on))
            application.add_handler(CommandHandler("pc_off", pc_off))
            application.add_handler(CommandHandler("pc_status", pc_status))
        if "gate" in enabled:
            application.add_handler(CommandHandler("gate_open", gate_open))
            application.add_handler(CommandHandler("entrada", gate_entrada))
            application.add_handler(CommandHandler("salida", gate_salida))
            application.add_handler(CommandHandler("invite", invite))
            application.add_handler(CommandHandler("gate_invite_link", invite_link_gate))
            application.add_handler(CommandHandler("gate_invite", invite_gate))
        if "acestep" in enabled:
            application.add_handler(CommandHandler("acestep_start", acestep_start))
            application.add_handler(CommandHandler("acestep_stop", acestep_stop))
            application.add_handler(CommandHandler("save_song", acestep_save))
            application.add_handler(CommandHandler("invite_link", invite_link))
            application.add_handler(CommandHandler("invite_songs", invite_songs))
            application.add_handler(CommandHandler("grant_songs", grant_songs))
            application.add_handler(CommandHandler("request_songs", solicitar_canciones))
            application.add_handler(CommandHandler("invitations_status", estado_invitaciones))
            application.add_handler(CallbackQueryHandler(save_admin_song_callback, pattern="^save_admin_song$"))
        if "ollama" in enabled:
            application.add_handler(CommandHandler("ollama_start", ollama_start))
            application.add_handler(CommandHandler("ollama_stop", ollama_stop))
        if "acestep" in enabled:
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("generate_song", generate_song_start)],
                states={
                    MODE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_mode)],
                    LYRICS_OR_STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_or_style)],
                    AI_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ai_prompt)],
                    AI_LANGUAGE: [
                        CallbackQueryHandler(generate_song_language_callback, pattern="^lang_"),
                        MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ask_language_buttons),
                    ],
                    AI_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ai_review)],
                    STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_style)],
                    LYRICS_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_choice)],
                    LYRICS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_text)],
                },
                fallbacks=[CommandHandler("cancel", generate_song_cancel)],
            )
            application.add_handler(conv_handler)
    elif mode == "songs":
        application.add_handler(CommandHandler("request_songs", solicitar_canciones))
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("generate_song", generate_song_start)],
            states={
                MODE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_mode)],
                LYRICS_OR_STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_or_style)],
                AI_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ai_prompt)],
                AI_LANGUAGE: [
                    CallbackQueryHandler(generate_song_language_callback, pattern="^lang_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ask_language_buttons),
                ],
                AI_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ai_review)],
                STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_style)],
                LYRICS_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_choice)],
                LYRICS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_text)],
            },
            fallbacks=[CommandHandler("cancel", generate_song_cancel)],
        )
        application.add_handler(conv_handler)
    elif mode == "gate":
        application.add_handler(CommandHandler("gate_open", gate_open))
        application.add_handler(CommandHandler("entrada", gate_entrada))
        application.add_handler(CommandHandler("salida", gate_salida))

    return application

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Memory optimization: Tune GC
    gc.set_threshold(400, 5, 5)
    
    # Startup
    logger.info("Initializing database...")
    await init_db()
    
    # Ensure admin user exists
    async with AsyncSessionLocal() as session:
        perm_service = PermissionService(session)
        await perm_service.ensure_admin(settings.ADMIN_TELEGRAM_ID)
    
    # Initialize Event Bus
    bus = EventBus()
    app.state.bus = bus
    
    # Initialize Modules
    enabled = get_enabled_modules()
    notifier = Notifier(bus)
    modules = [
        StateStore(bus),
        CommandRouter(bus),
        notifier
    ]
    
    if "zigbee" in enabled:
        modules.append(ZigbeeAdapter(bus))
    if "arlo" in enabled:
        modules.append(ArloAdapter(bus))
    if "scheduler" in enabled:
        modules.append(SchedulerModule(bus))
    if "pc" in enabled:
        modules.append(PCController(bus))
    if "gate" in enabled:
        modules.append(GateController(bus))
    if "pc" in enabled or "gate" in enabled: # Permission is usually needed for core features
        modules.append(PermissionController(bus))
    if "acestep" in enabled:
        modules.append(AceStepController(bus))
        
    app.state.modules = modules
    
    # Start Modules
    for module in modules:
        await module.start()
    
    logger.info("Starting Telegram bot...")
    application = setup_bot()
    notifier.bot_app = application
    application.bot_data["bus"] = bus
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
    except InvalidToken:
        logger.error(
            "Telegram BOT_TOKEN was rejected by the server (401 Unauthorized). "
            "Check BOT_TOKEN in .env: it must be valid and not revoked. "
            "Create or regenerate a token at https://t.me/BotFather."
        )
        sys.exit(3)
    app.state.bot_app = application

    yield
    
    # Shutdown
    logger.info("Shutting down modules...")
    for module in reversed(app.state.modules):
        await module.stop()
        
    logger.info("Shutting down Telegram bot...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

app = FastAPI(title="RaspiHomeBot API", lifespan=lifespan)
app.include_router(api_router)
app.include_router(db_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
