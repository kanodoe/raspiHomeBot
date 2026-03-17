import pytest
from app.services.usage_service import UsageService
from app.database.models import AccessRequestStatus

@pytest.mark.asyncio
async def test_log_operation(db_session):
    service = UsageService(db_session)
    op = await service.log_operation(123, "test_op", metadata="test_meta", display_name="Test User")
    
    assert op.telegram_id == 123
    assert op.operation_type == "test_op"
    assert op.metadata_ == "test_meta"
    assert op.display_name == "Test User"

@pytest.mark.asyncio
async def test_create_access_request(db_session):
    service = UsageService(db_session)
    req = await service.create_access_request(456, "more_songs", requested_value="+5")
    
    assert req.telegram_id == 456
    assert req.request_type == "more_songs"
    assert req.requested_value == "+5"
    assert req.status == AccessRequestStatus.PENDING.value

@pytest.mark.asyncio
async def test_resolve_access_request(db_session):
    service = UsageService(db_session)
    req = await service.create_access_request(456, "more_songs")
    
    resolved = await service.resolve_access_request(
        req.id, 
        AccessRequestStatus.APPROVED.value, 
        responded_by=123, 
        notes="Approved by admin"
    )
    
    assert resolved.status == AccessRequestStatus.APPROVED.value
    assert resolved.responded_by == 123
    assert resolved.notes == "Approved by admin"
    assert resolved.responded_at is not None

@pytest.mark.asyncio
async def test_list_access_requests(db_session):
    service = UsageService(db_session)
    await service.create_access_request(111, "type1")
    await service.create_access_request(222, "type2")
    
    requests = await service.list_access_requests()
    assert len(requests) == 2
    
    # Filter by telegram_id
    user_requests = await service.list_access_requests(telegram_id=111)
    assert len(user_requests) == 1
    assert user_requests[0].telegram_id == 111
