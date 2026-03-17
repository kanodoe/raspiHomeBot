import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock

from main import lifespan
from app.core.config import settings
from app.database.models import User, UserRole, UserQuota
from app.database.session import get_db

@pytest_asyncio.fixture
async def app_test(db_session, engine):
    """
    Crea una instancia de FastAPI con el lifespan ejecutado (módulos, bus, etc)
    pero mockeando el bot de Telegram y usando la base de datos de prueba.
    """
    # Sobrescribimos get_db para que use la sesión de prueba de la fixture
    def _get_test_db():
        yield db_session

    app = FastAPI(lifespan=lifespan)
    from app.api.routes import router as api_router
    from app.api.db_routes import router as db_router
    app.include_router(api_router)
    app.include_router(db_router)
    
    app.dependency_overrides[get_db] = _get_test_db
    
    # Mockear setup_bot para que no intente conectar a Telegram real
    import main
    original_setup_bot = main.setup_bot
    mock_app = MagicMock()
    mock_app.initialize = AsyncMock()
    mock_app.start = AsyncMock()
    mock_app.updater.start_polling = AsyncMock()
    mock_app.updater.stop = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    mock_app.bot_data = {}
    main.setup_bot = MagicMock(return_value=mock_app)

    async with lifespan(app):
        yield app
    
    main.setup_bot = original_setup_bot

@pytest.mark.asyncio
async def test_register_guest_endpoint(app_test, db_session):
    """Prueba el endpoint de registro de invitados con cuota y notificación."""
    transport = ASGITransport(app=app_test)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Configurar API_KEY si existe
        headers = {}
        if settings.API_KEY:
            headers["X-Api-Key"] = settings.API_KEY
        
        # 2. Datos del nuevo invitado
        payload = {
            "telegram_id": 123456789,
            "song_quota": 5,
            "username": "test_guest",
            "first_name": "Test",
            "last_name": "Guest"
        }
        
        # 3. Llamar al endpoint
        response = await ac.post("/api/register-guest", json=payload, headers=headers)
        
        # 4. Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user"]["telegram_id"] == 123456789
        assert data["quota_added"] == 5
        
        # 5. Verificar en la base de datos
        from sqlalchemy import select
        # Verificar usuario
        result = await db_session.execute(select(User).where(User.telegram_id == 123456789))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.role == UserRole.GUEST
        assert user.username == "test_guest"
        
        # Verificar cuota
        result = await db_session.execute(
            select(UserQuota).where(
                UserQuota.telegram_id == 123456789, 
                UserQuota.access_type == "song"
            )
        )
        quota = result.scalar_one_or_none()
        assert quota is not None
        assert quota.song_quota == 5
        
        # 6. (Opcional) Verificar que se intentó notificar
        # Como app.state.bus es el EventBus real, pero Notifier.bot_app es un mock,
        # podemos verificar que se llamó al bot mockeado.
        # Buscamos el notifier en los módulos
        notifier = None
        for m in app_test.state.modules:
            from app.modules.notifier import Notifier
            if isinstance(m, Notifier):
                notifier = m
                break
        
        assert notifier is not None
        # Esperar un poco a que el evento se procese (es asíncrono en el bus)
        import asyncio
        await asyncio.sleep(0.1)
        
        # El bot real enviaría un mensaje, aquí verificamos el mock del bot
        # notifier.bot_app.bot.send_message
        assert notifier.bot_app.bot.send_message.called
        args, kwargs = notifier.bot_app.bot.send_message.call_args
        assert kwargs["chat_id"] == 123456789
        assert "cupo de 5 canciones" in kwargs["text"]
