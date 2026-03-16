import uvicorn
import gc
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler

from app.core.config import settings
from app.core.logging import logger
from app.core.event_bus import EventBus
from app.api.routes import router as api_router
from app.database.session import init_db, AsyncSessionLocal
from app.services.permission_service import PermissionService
from app.bot.handlers import (
    pc_on, pc_off, pc_status, status_summary, gate_open, invite, start,
    acestep_start, acestep_stop, ollama_start, ollama_stop,
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
async def register_commands(bot):
    commands = [
        BotCommand("start", "Ver mi ID y estado del bot"),
        BotCommand("pc_on", "Encender PC (WOL)"),
        BotCommand("pc_off", "Apagar PC (SSH)"),
        BotCommand("pc_status", "Estado de red del PC"),
        BotCommand("status", "Resumen del sistema"),
        BotCommand("gate_open", "Abrir el portón (Invitados)"),
        BotCommand("invite", "Invitar usuario (Admin)"),
        BotCommand("acestep_start", "Iniciar ACE-Step API"),
        BotCommand("acestep_stop", "Detener ACE-Step API"),
        BotCommand("ollama_start", "Iniciar Ollama"),
        BotCommand("ollama_stop", "Detener Ollama"),
        BotCommand("generate_song", "Generar una canción (AI)")
    ]
    await bot.set_my_commands(commands)
    logger.info("Telegram bot commands registered in API.")

def setup_bot():
    application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pc_on", pc_on))
    application.add_handler(CommandHandler("pc_off", pc_off))
    application.add_handler(CommandHandler("pc_status", pc_status))
    application.add_handler(CommandHandler("status", status_summary))
    application.add_handler(CommandHandler("gate_open", gate_open))
    application.add_handler(CommandHandler("invite", invite))
    application.add_handler(CommandHandler("acestep_start", acestep_start))
    application.add_handler(CommandHandler("acestep_stop", acestep_stop))
    application.add_handler(CommandHandler("ollama_start", ollama_start))
    application.add_handler(CommandHandler("ollama_stop", ollama_stop))

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
    notifier = Notifier(bus)
    modules = [
        StateStore(bus),
        CommandRouter(bus),
        ZigbeeAdapter(bus),
        ArloAdapter(bus),
        SchedulerModule(bus),
        notifier,
        PCController(bus),
        GateController(bus),
        PermissionController(bus),
        AceStepController(bus)
    ]
    app.state.modules = modules
    
    # Start Modules
    for module in modules:
        await module.start()
    
    logger.info("Starting Telegram bot...")
    application = setup_bot()
    notifier.bot_app = application
    application.bot_data["bus"] = bus
    await application.initialize()
    await register_commands(application.bot)
    await application.start()
    await application.updater.start_polling()
    
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
