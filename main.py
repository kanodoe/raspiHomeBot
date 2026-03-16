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
from app.database.session import init_db, AsyncSessionLocal
from app.services.permission_service import PermissionService
from app.bot.handlers import (
    pc_on, pc_off, pc_status, status_summary, gate_open, invite, start,
    acestep_start, acestep_stop, acestep_save, ollama_start, ollama_stop,
    generate_song_start, generate_song_mode, generate_song_style, 
    generate_song_lyrics_choice, generate_song_lyrics_text, 
    generate_song_ai_prompt, generate_song_ai_review, generate_song_cancel,
    MODE_SELECT, STYLE, LYRICS_CHOICE, LYRICS_TEXT, AI_PROMPT, AI_REVIEW
)
from telegram.ext import ApplicationBuilder, CommandHandler, ConversationHandler, MessageHandler, filters

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

async def register_commands(bot):
    enabled = get_enabled_modules()
    commands = [BotCommand("start", "Ver mi ID y estado del bot")]
    
    if "pc" in enabled:
        commands.extend([
            BotCommand("pc_on", "Encender PC (WOL)"),
            BotCommand("pc_off", "Apagar PC (SSH)"),
            BotCommand("pc_status", "Estado de red del PC"),
        ])
    
    if "gate" in enabled:
        commands.append(BotCommand("gate_open", "Abrir el portón (Invitados)"))
        commands.append(BotCommand("invite", "Invitar usuario (Admin)"))
    
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
        
    if "acestep" in enabled: # Generate song needs acestep
        commands.append(BotCommand("generate_song", "Generar una canción (AI)"))
        
    await bot.set_my_commands(commands)
    logger.info("Telegram bot commands registered in API.")

def setup_bot():
    enabled = get_enabled_modules()
    application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_summary))

    if "pc" in enabled:
        application.add_handler(CommandHandler("pc_on", pc_on))
        application.add_handler(CommandHandler("pc_off", pc_off))
        application.add_handler(CommandHandler("pc_status", pc_status))

    if "gate" in enabled:
        application.add_handler(CommandHandler("gate_open", gate_open))
        application.add_handler(CommandHandler("invite", invite))

    if "acestep" in enabled:
        application.add_handler(CommandHandler("acestep_start", acestep_start))
        application.add_handler(CommandHandler("acestep_stop", acestep_stop))
        application.add_handler(CommandHandler("save_song", acestep_save))

    if "ollama" in enabled:
        application.add_handler(CommandHandler("ollama_start", ollama_start))
        application.add_handler(CommandHandler("ollama_stop", ollama_stop))

    if "acestep" in enabled:
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("generate_song", generate_song_start)],
            states={
                MODE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_mode)],
                AI_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ai_prompt)],
                AI_REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_ai_review)],
                STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_style)],
                LYRICS_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_choice)],
                LYRICS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_song_lyrics_text)],
            },
            fallbacks=[CommandHandler("cancel", generate_song_cancel)],
        )
        application.add_handler(conv_handler)
    
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
        await register_commands(application.bot)
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
