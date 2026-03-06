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

@restricted(UserRole.GUEST)
async def pc_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bus = context.bot_data.get("bus")
    if bus:
        await bus.publish("command", {"command": "pc_status", "source": f"chat_{update.effective_chat.id}"})
    else:
        from app.services.wol_service import WOLService
        status = await WOLService.get_pc_status()
        await update.message.reply_text(f"PC Status: {status}")

@restricted(UserRole.GUEST)
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
