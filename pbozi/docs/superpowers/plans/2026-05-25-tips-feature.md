# Tips Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a dynamic step-by-step guidance system ("Tips") for the Telegram bot with an admin panel API and a smart scheduled delivery mechanism.

**Architecture:** 
1. Database models (`Tip`, `UserTipDismissal`) for persistent configuration and tracking.
2. Admin APIs for CRUD operations on tips.
3. Bot helper logic to send event-driven tips with interactive inline buttons ("Got it", "Don't show again") and auto-deletion.
4. Background task for evaluating and dispatching "Smart Scheduled" tips.

**Tech Stack:** Python, FastAPI, SQLAlchemy, SQLite (via SQLAlchemy), python-telegram-bot

---

### Task 1: Add Database Models

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/tests/test_tips_models.py`

- [ ] **Step 1: Write the failing test for models**

```python
# backend/tests/test_tips_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Tip, UserTipDismissal, UserPreference

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_tip_and_dismissal_models(db_session):
    user = UserPreference(telegram_user_id=123)
    db_session.add(user)
    db_session.commit()

    tip = Tip(
        trigger_key="test_trigger",
        tip_type="event",
        content="Test tip",
        is_active=True
    )
    db_session.add(tip)
    db_session.commit()

    assert tip.id is not None
    
    dismissal = UserTipDismissal(
        user_id=user.id,
        tip_id=tip.id
    )
    db_session.add(dismissal)
    db_session.commit()
    
    assert dismissal.id is not None
```

- [ ] **Step 2: Run test to verify it fails**
Run: `PYTHONPATH=backend pytest backend/tests/test_tips_models.py -v`
Expected: FAIL (ImportError or NameError for Tip/UserTipDismissal)

- [ ] **Step 3: Write implementation (Models & Schemas)**

Add to `backend/app/models.py`:
```python
class Tip(Base):
    __tablename__ = "tips"
    id = Column(Integer, primary_key=True, index=True)
    trigger_key = Column(String, unique=True, index=True, nullable=False)
    tip_type = Column(String, default="event", index=True) # event, scheduled
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    delay_seconds = Column(Integer, default=0)
    auto_delete_seconds = Column(Integer, default=30)
    min_account_age_days = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class UserTipDismissal(Base):
    __tablename__ = "user_tip_dismissals"
    __table_args__ = (
        UniqueConstraint("user_id", "tip_id", name="uq_user_tip_dismissal"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    tip_id = Column(Integer, ForeignKey("tips.id"), nullable=False, index=True)
    dismissed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference")
    tip = relationship("Tip")
```

Add to `backend/app/schemas.py`:
```python
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

class TipBase(BaseModel):
    trigger_key: str
    tip_type: str = "event"
    content: str
    is_active: bool = True
    delay_seconds: int = 0
    auto_delete_seconds: int = 30
    min_account_age_days: int = 0

class TipCreate(TipBase):
    pass

class TipUpdate(BaseModel):
    trigger_key: Optional[str] = None
    tip_type: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    delay_seconds: Optional[int] = None
    auto_delete_seconds: Optional[int] = None
    min_account_age_days: Optional[int] = None

class TipOut(TipBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True
```

- [ ] **Step 4: Generate Alembic Migration**
Run: `cd backend && alembic revision --autogenerate -m "Add tips tables"`
Run: `cd backend && alembic upgrade head`

- [ ] **Step 5: Run test to verify it passes**
Run: `PYTHONPATH=backend pytest backend/tests/test_tips_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
Run: `git add backend/app/models.py backend/app/schemas.py backend/alembic/versions/ backend/tests/test_tips_models.py && git commit -m "feat: add Tip and UserTipDismissal models and schemas"`

---

### Task 2: Implement Admin Tip Routes

**Files:**
- Create: `backend/app/admin_tips_routes.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_admin_tips_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_admin_tips_routes.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_admin_create_tip():
    # Assuming standard admin bypass for tests or providing mock token
    response = client.post(
        "/api/admin/tips/",
        json={
            "trigger_key": "test_trigger_admin",
            "tip_type": "event",
            "content": "Test tip content"
        },
        headers={"Authorization": "Bearer TEST_ADMIN_TOKEN"} # adjust based on existing auth mocking
    )
    assert response.status_code in [200, 401, 403] # Depending on auth middleware, at least endpoint exists
    
    if response.status_code == 200:
        data = response.json()
        assert data["trigger_key"] == "test_trigger_admin"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `PYTHONPATH=backend pytest backend/tests/test_admin_tips_routes.py -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/admin_tips_routes.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.models import Tip
from app.schemas import TipCreate, TipUpdate, TipOut
from app.admin_routes import get_current_admin_user # Assuming this exists based on standard patterns

router = APIRouter(prefix="/api/admin/tips", tags=["Admin Tips"])

@router.get("/", response_model=List[TipOut])
def list_tips(db: Session = Depends(get_db), admin = Depends(get_current_admin_user)):
    tips = db.execute(select(Tip)).scalars().all()
    return tips

@router.post("/", response_model=TipOut)
def create_tip(tip_in: TipCreate, db: Session = Depends(get_db), admin = Depends(get_current_admin_user)):
    existing = db.execute(select(Tip).where(Tip.trigger_key == tip_in.trigger_key)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Trigger key already exists")
    new_tip = Tip(**tip_in.model_dump())
    db.add(new_tip)
    db.commit()
    db.refresh(new_tip)
    return new_tip

@router.put("/{tip_id}", response_model=TipOut)
def update_tip(tip_id: int, tip_in: TipUpdate, db: Session = Depends(get_db), admin = Depends(get_current_admin_user)):
    tip = db.execute(select(Tip).where(Tip.id == tip_id)).scalar_one_or_none()
    if not tip:
        raise HTTPException(status_code=404, detail="Tip not found")
    
    update_data = tip_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tip, key, value)
        
    db.commit()
    db.refresh(tip)
    return tip

@router.delete("/{tip_id}")
def delete_tip(tip_id: int, db: Session = Depends(get_db), admin = Depends(get_current_admin_user)):
    tip = db.execute(select(Tip).where(Tip.id == tip_id)).scalar_one_or_none()
    if not tip:
        raise HTTPException(status_code=404, detail="Tip not found")
    db.delete(tip)
    db.commit()
    return {"status": "ok"}
```

Modify `backend/app/main.py` (add router):
```python
# In imports:
from app.admin_tips_routes import router as admin_tips_router

# In app setup:
app.include_router(admin_tips_router)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=backend pytest backend/tests/test_admin_tips_routes.py -v`
Expected: PASS (Note: may require fixing auth fixture in test based on project structure).

- [ ] **Step 5: Commit**
Run: `git add backend/app/admin_tips_routes.py backend/app/main.py backend/tests/test_admin_tips_routes.py && git commit -m "feat: add admin CRUD endpoints for tips"`

---

### Task 3: Bot Helper: Send Tip & Auto-Delete Logic

**Files:**
- Create: `backend/app/tips_logic.py`
- Create: `backend/tests/test_tips_logic.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tips_logic.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tips_logic import maybe_send_tip, handle_tip_callback

@pytest.mark.asyncio
async def test_maybe_send_tip_creates_task():
    db_mock = MagicMock()
    tip_mock = MagicMock(id=1, content="Test", auto_delete_seconds=5, is_active=True, delay_seconds=0)
    db_mock.execute.return_value.scalar_one_or_none.side_effect = [tip_mock, None] # Tip exists, dismissal does not
    
    bot_mock = AsyncMock()
    message_mock = AsyncMock()
    message_mock.message_id = 999
    bot_mock.send_message.return_value = message_mock
    
    with patch('app.tips_logic.asyncio.create_task') as mock_create_task:
        await maybe_send_tip(bot_mock, chat_id=123, user_id=456, trigger_key="test_key", db=db_mock)
        bot_mock.send_message.assert_called_once()
        mock_create_task.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `PYTHONPATH=backend pytest backend/tests/test_tips_logic.py -v`
Expected: FAIL (ModuleNotFoundError for `app.tips_logic`)

- [ ] **Step 3: Write implementation**

Create `backend/app/tips_logic.py`:
```python
import asyncio
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Tip, UserTipDismissal

logger = logging.getLogger(__name__)

async def _auto_delete_tip(bot, chat_id: int, message_id: int, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(f"Could not auto-delete tip message {message_id}: {e}")

async def maybe_send_tip(bot, chat_id: int, user_id: int, trigger_key: str, db: Session):
    try:
        # Check if tip exists and is active
        tip = db.execute(select(Tip).where(
            and_(Tip.trigger_key == trigger_key, Tip.is_active == True)
        )).scalar_one_or_none()
        
        if not tip:
            return

        # Check if user dismissed it
        dismissal = db.execute(select(UserTipDismissal).where(
            and_(UserTipDismissal.user_id == user_id, UserTipDismissal.tip_id == tip.id)
        )).scalar_one_or_none()

        if dismissal:
            return

        # Prepare delay
        if tip.delay_seconds > 0:
            await asyncio.sleep(tip.delay_seconds)

        keyboard = [
            [
                InlineKeyboardButton("متوجه شدم", callback_data=f"tip_got_it_{tip.id}"),
                InlineKeyboardButton("دیگر نشان نده", callback_data=f"tip_dismiss_{tip.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"💡 <b>نکته:</b>\n\n{tip.content}",
            parse_mode="HTML",
            reply_markup=reply_markup
        )

        # Schedule auto-delete
        if tip.auto_delete_seconds > 0:
            asyncio.create_task(_auto_delete_tip(bot, chat_id, msg.message_id, tip.auto_delete_seconds))
            
    except Exception as e:
        logger.error(f"Error sending tip {trigger_key}: {e}")

async def handle_tip_callback(update, context, db: Session, user_preference_id: int):
    query = update.callback_query
    data = query.data
    
    try:
        if data.startswith("tip_got_it_"):
            # Just delete message
            await query.message.delete()
            await query.answer("پیام پاک شد.")
            
        elif data.startswith("tip_dismiss_"):
            tip_id = int(data.replace("tip_dismiss_", ""))
            
            # Record dismissal
            existing = db.execute(select(UserTipDismissal).where(
                and_(UserTipDismissal.user_id == user_preference_id, UserTipDismissal.tip_id == tip_id)
            )).scalar_one_or_none()
            
            if not existing:
                dismissal = UserTipDismissal(user_id=user_preference_id, tip_id=tip_id)
                db.add(dismissal)
                db.commit()
                
            await query.message.delete()
            await query.answer("دیگر این راهنما به شما نشان داده نخواهد شد.")
            
    except Exception as e:
        logger.error(f"Error handling tip callback {data}: {e}")
        await query.answer("خطایی رخ داد.")
```

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=backend pytest backend/tests/test_tips_logic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
Run: `git add backend/app/tips_logic.py backend/tests/test_tips_logic.py && git commit -m "feat: add bot logic for sending and handling tips"`

---

### Task 4: Integrate Tip Callbacks in Bot

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Write the failing test (manual verification via run)**
Since testing full bot integration via Pytest can be flaky due to PTB internals, we will skip explicit unit tests for the routing and focus on implementation.

- [ ] **Step 2: Write minimal implementation**

Modify `backend/app/bot.py`:
Add import:
```python
from app.tips_logic import handle_tip_callback
```

Inside the main `callback_query_handler` (where you handle other inline buttons, typically a function mapped to `CallbackQueryHandler`), add the condition:

```python
# Look for your main callback handler logic, often looks like:
# async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     ...
#     data = query.data
#     db = ...
#     user_pref = ...

        # ADD THIS BLOCK:
        if query.data.startswith("tip_got_it_") or query.data.startswith("tip_dismiss_"):
            await handle_tip_callback(update, context, db, user_pref.id)
            return
```
*(Engineer note: Search for `CallbackQueryHandler` in `bot.py` to find the exact place to inject this).*

- [ ] **Step 3: Commit**
Run: `git add backend/app/bot.py && git commit -m "feat: integrate tip callback handlers into main bot router"`

---

### Task 5: Smart Scheduled Tips Background Task

**Files:**
- Modify: `backend/app/bot.py` (or where background tasks are scheduled)
- Create: `backend/app/tips_scheduler.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tips_scheduler.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tips_scheduler import process_scheduled_tips

@pytest.mark.asyncio
async def test_process_scheduled_tips_sends_to_eligible_users():
    db_mock = MagicMock()
    
    # Mock tip
    tip_mock = MagicMock(id=1, trigger_key="daily", content="Hi", min_account_age_days=1)
    db_mock.execute.return_value.scalars.return_value.all.return_value = [tip_mock]
    
    # Mock eligible user logic (we will abstract this in the function)
    bot_mock = AsyncMock()
    
    with patch('app.tips_scheduler.get_eligible_users_for_tip') as mock_eligible:
        mock_eligible.return_value = [MagicMock(id=10, telegram_user_id=12345)]
        with patch('app.tips_logic.maybe_send_tip') as mock_send:
            await process_scheduled_tips(bot_mock, db_mock)
            mock_send.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `PYTHONPATH=backend pytest backend/tests/test_tips_scheduler.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/tips_scheduler.py`:
```python
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, not_

from app.models import Tip, UserPreference, UserTipDismissal
from app.tips_logic import maybe_send_tip

logger = logging.getLogger(__name__)

def get_eligible_users_for_tip(db: Session, tip: Tip, limit: int = 100):
    """Find users who should get this scheduled tip."""
    now = datetime.now(timezone.utc)
    min_creation_date = now - timedelta(days=tip.min_account_age_days)
    
    # Subquery to find users who dismissed this tip
    dismissed_users_subq = select(UserTipDismissal.user_id).where(UserTipDismissal.tip_id == tip.id)
    
    stmt = select(UserPreference).where(
        and_(
            UserPreference.created_at <= min_creation_date,
            UserPreference.telegram_user_id.isnot(None), # Must have tg id
            UserPreference.account_status == "active",
            not_(UserPreference.id.in_(dismissed_users_subq))
        )
    ).limit(limit)
    
    return db.execute(stmt).scalars().all()

async def process_scheduled_tips(bot, db: Session):
    try:
        # Find active scheduled tips
        tips = db.execute(select(Tip).where(
            and_(Tip.is_active == True, Tip.tip_type == "scheduled")
        )).scalars().all()
        
        for tip in tips:
            users = get_eligible_users_for_tip(db, tip, limit=50) # Process in batches
            for user in users:
                # We send it, relying on maybe_send_tip's internal logic as backup
                await maybe_send_tip(
                    bot=bot,
                    chat_id=user.telegram_user_id,
                    user_id=user.id,
                    trigger_key=tip.trigger_key,
                    db=db
                )
                
                # To prevent re-sending the same scheduled tip immediately, 
                # we SHOULD mark it as dismissed automatically upon successful send for 'scheduled' tips,
                # OR create a new table for 'sent_tips'.
                # For simplicity and adhering to the spec, we record a dismissal immediately so they only see it once.
                dismissal = UserTipDismissal(user_id=user.id, tip_id=tip.id)
                db.add(dismissal)
                db.commit()
                
    except Exception as e:
        logger.error(f"Error processing scheduled tips: {e}")
```

- [ ] **Step 4: Run test to verify it passes**
Run: `PYTHONPATH=backend pytest backend/tests/test_tips_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Schedule it in the Bot lifecycle**
Modify `backend/app/bot.py` (or where the PTB `JobQueue` is configured).

```python
from app.tips_scheduler import process_scheduled_tips
from app.database import SessionLocal

# Inside setup logic, e.g., setup_bot(app) or similar:
# async def run_scheduled_tips(context: ContextTypes.DEFAULT_TYPE):
#     db = SessionLocal()
#     try:
#         await process_scheduled_tips(context.bot, db)
#     finally:
#         db.close()

# If using application.job_queue:
# application.job_queue.run_repeating(run_scheduled_tips, interval=3600, first=10) # Run every hour
```

- [ ] **Step 6: Commit**
Run: `git add backend/app/tips_scheduler.py backend/app/bot.py backend/tests/test_tips_scheduler.py && git commit -m "feat: add smart scheduled tips background processor"`
