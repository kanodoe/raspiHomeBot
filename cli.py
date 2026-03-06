import asyncio
import argparse
import traceback
from typing import List

# Import project components
from app.core.config import settings
from app.database.session import init_db, AsyncSessionLocal
from app.services.permission_service import PermissionService
from app.bot.handlers import pc_on, pc_off, pc_status, status_summary, gate_open, invite

# Mock classes to simulate python-telegram-bot objects
class MockUser:
    def __init__(self, user_id: int, username: str = "CLI_User"):
        self.id = user_id
        self.username = username
        self.is_bot = False
        self.first_name = "CLI"
        self.last_name = "User"

class MockChat:
    def __init__(self, chat_id: int):
        self.id = chat_id
        self.type = "private"

class MockMessage:
    def __init__(self, user: MockUser, chat_id: int, text: str = ""):
        self.from_user = user
        self.chat_id = chat_id
        self.text = text
    
    async def reply_text(self, text: str, **kwargs):
        print(f"\n[BOT REPLY] -> {text}")

class MockUpdate:
    def __init__(self, user: MockUser, chat_id: int, text: str = ""):
        self.effective_user = user
        self.effective_chat = MockChat(chat_id)
        self.message = MockMessage(user, chat_id, text)

class MockBot:
    async def send_message(self, chat_id: int, text: str, **kwargs):
        print(f"\n[BOT SEND_MESSAGE ({chat_id})] -> {text}")

class MockContext:
    def __init__(self, args: List[str] = None):
        self.bot = MockBot()
        self.args = args or []

async def run_command(command_name: str, args: List[str], user_id: int, chat_id: int):
    # Initialize DB and ensure admin user exists
    await init_db()
    async with AsyncSessionLocal() as session:
        perm_service = PermissionService(session)
        await perm_service.ensure_admin(settings.ADMIN_TELEGRAM_ID)

    # Command map (same as in main.py)
    handlers = {
        "pc_on": pc_on,
        "pc_off": pc_off,
        "pc_status": pc_status,
        "status": status_summary,
        "gate_open": gate_open,
        "invite": invite
    }

    # Normalize command name
    cmd = command_name.lstrip("/")
    if cmd not in handlers:
        print(f"Error: Unknown command '{command_name}'")
        print(f"Available commands: {', '.join(f'/{c}' for c in handlers.keys())}")
        return

    handler = handlers[cmd]
    
    # Create mocks
    user = MockUser(user_id)
    update = MockUpdate(user, chat_id, text=f"/{cmd} {' '.join(args)}")
    context = MockContext(args)

    print(f"--- Simulating /{cmd} for User ID: {user_id} ---")
    
    try:
        await handler(update, context)
        
        # If it's pc_on, wait a bit for background tasks
        if cmd == "pc_on":
            print("\n(WOL packet sent. Monitoring started. Waiting 5s for an update...)")
            await asyncio.sleep(5)
            
    except Exception as e:
        print(f"\n[ERROR] Exception during handler execution: {e}")
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="RaspiHomeBot Telegram CLI Simulator")
    parser.add_argument("command", help="The command to simulate (e.g., /status)")
    parser.add_argument("args", nargs="*", help="Arguments for the command (e.g., user_id duration for /invite)")
    parser.add_argument("--user-id", type=int, help="Telegram User ID to simulate (defaults to ADMIN_TELEGRAM_ID)")
    parser.add_argument("--chat-id", type=int, help="Telegram Chat ID to simulate (defaults to user-id)")

    cli_args = parser.parse_args()
    
    # If user-id is not provided, use the admin ID from settings
    user_id = cli_args.user_id if cli_args.user_id is not None else settings.ADMIN_TELEGRAM_ID
    chat_id = cli_args.chat_id if cli_args.chat_id is not None else user_id

    try:
        asyncio.run(run_command(cli_args.command, cli_args.args, user_id, chat_id))
    except KeyboardInterrupt:
        print("\nSimulation stopped.")
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
