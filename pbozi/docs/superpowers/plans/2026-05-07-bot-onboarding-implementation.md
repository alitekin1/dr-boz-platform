# Bot Onboarding & Admin Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve bot onboarding with scenarios, targeted admin broadcasts for referrals, and custom button support in admin messages.

**Architecture:** Database-driven configuration for scenarios and buttons. Backend APIs for admin management. Bot handlers for specific callback patterns.

**Tech Stack:** Python (FastAPI, SQLAlchemy, python-telegram-bot), React (Tailwind/Vanilla CSS).

---

### Task 1: Database Models

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add BotStartScenario and AdminMessageButton models**

```python
class BotStartScenario(Base):
    __tablename__ = "bot_start_scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

class AdminMessageButton(Base):
    __tablename__ = "admin_message_buttons"
    id: Mapped[int] = mapped_column(primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
```

- [ ] **Step 2: Verify models and commit**

```bash
git add backend/app/models.py
git commit -m "feat: add models for scenarios and admin buttons"
```

---

### Task 2: Backend API for Start Scenarios

**Files:**
- Modify: `backend/app/admin_routes.py` (or create a new file if preferred, but following patterns)
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add Schemas**

```python
class BotStartScenarioSchema(BaseModel):
    id: int
    label: str
    prompt: str
    order: int
    is_active: bool
    class Config: from_attributes = True

class BotStartScenarioCreate(BaseModel):
    label: str
    prompt: str
    order: int = 0
    is_active: bool = True
```

- [ ] **Step 2: Add Admin Routes for Scenarios**

```python
@router.get("/start-scenarios", response_model=List[BotStartScenarioSchema])
async def get_start_scenarios(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BotStartScenario).order_by(BotStartScenario.order))
    return result.scalars().all()

@router.post("/start-scenarios", response_model=BotStartScenarioSchema)
async def create_start_scenario(data: BotStartScenarioCreate, db: AsyncSession = Depends(get_db)):
    scenario = BotStartScenario(**data.dict())
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return scenario
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/admin_routes.py backend/app/schemas.py
git commit -m "feat: add admin routes for bot start scenarios"
```

---

### Task 3: Bot Onboarding Implementation

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update cmd_start to include scenario buttons**

```python
# Inside cmd_start
        scenarios_res = await db.execute(
            select(BotStartScenario).where(BotStartScenario.is_active == True).order_by(BotStartScenario.order)
        )
        scenarios = scenarios_res.scalars().all()
        
        kb_buttons = []
        for s in scenarios:
            kb_buttons.append([InlineKeyboardButton(s.label, callback_data=f"scenario_start_{s.id}")])
        
        reply_markup = InlineKeyboardMarkup(kb_buttons) if kb_buttons else main_kb(uid == ADMIN_ID)
        
        await update.message.reply_text(start_intro_text or "سلام 👋 چطوری کمکت کنم؟", reply_markup=reply_markup)
```

- [ ] **Step 2: Implement callback handler for scenario_start**

```python
async def handle_scenario_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    scenario_id = int(data.split("_")[-1])
    
    async with async_session() as db:
        scenario = await db.get(BotStartScenario, scenario_id)
        if not scenario:
            await query.edit_message_text("این سناریو دیگر در دسترس نیست.")
            return
        
        # Simulate user sending the prompt
        update.message = query.message
        update.message.text = scenario.prompt
        await handle_message(update, context) # Reuse existing message handler
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: implement scenario-based onboarding in bot"
```

---

### Task 4: Targeted Referral Broadcast

**Files:**
- Modify: `backend/app/admin_routes.py`
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update broadcast endpoint to filter by referral_campaign_id**

```python
# In broadcast route
async def send_broadcast(message: str, referral_campaign_id: int = None, ...):
    query = select(User.id)
    if referral_campaign_id:
        query = query.where(User.referral_campaign_id == referral_campaign_id)
    # ... rest of logic
```

- [ ] **Step 2: Update Bot Message logic to support custom buttons**

```python
# In bot broadcast task
async def send_admin_broadcast(db, user_id, text, buttons_data):
    kb = None
    if buttons_data:
        kb_rows = []
        for btn in buttons_data:
            if btn['type'] == 'url':
                kb_rows.append([InlineKeyboardButton(btn['label'], url=btn['value'])])
            elif btn['type'] == 'prompt':
                # Save to AdminMessageButton first
                new_btn = AdminMessageButton(prompt=btn['value'])
                db.add(new_btn)
                await db.flush()
                kb_rows.append([InlineKeyboardButton(btn['label'], callback_data=f"admin_btn_{new_btn.id}")])
        kb = InlineKeyboardMarkup(kb_rows)
    
    await bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
```

- [ ] **Step 3: Implement admin_btn callback handler**

```python
async def handle_admin_btn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    btn_id = int(query.data.split("_")[-1])
    
    async with async_session() as db:
        btn = await db.get(AdminMessageButton, btn_id)
        if not btn: return
        
        update.message = query.message
        update.message.text = btn.prompt
        await handle_message(update, context)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/admin_routes.py backend/app/bot.py
git commit -m "feat: implement targeted referral broadcast and custom buttons"
```

---

### Task 5: Admin Panel Frontend Updates (UI for managing Scenarios & Buttons)

**Files:**
- Create/Modify: `frontend-v2/src/pages/AdminScenarios.tsx`
- Modify: `frontend-v2/src/pages/AdminBroadcast.tsx`

- [ ] **Step 1: Build Scenario Management Page**
- [ ] **Step 2: Add Button Builder to Broadcast Page**
- [ ] **Step 3: Add Referral Filter to Broadcast Page**

- [ ] **Step 4: Commit**

```bash
git add frontend-v2/src/
git commit -m "feat: add admin UI for scenarios and button broadcasts"
```
