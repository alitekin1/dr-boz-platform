# Default Model Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow administrators to designate a global "default model" in the admin panel to be used as a fallback for new users.

**Architecture:** Add an `is_default` boolean to the `models` table. Update FastAPI schemas and admin endpoints to manage this state, ensuring mutual exclusivity (only one default active model). Modify Telegram bot logic to utilize this default model. Update the React frontend configuration UI to include a checkbox on the model form and a "DEFAULT" badge in the model list.

**Tech Stack:** Python (FastAPI, SQLAlchemy, aiosqlite), React (TypeScript, Vite, Tailwind CSS), SQLite.

---

### Task 1: Database Schema & Migration

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/database.py`

- [ ] **Step 1: Update Model SQLAlchemy Schema**
Modify `backend/app/models.py`. Add the `is_default` column to the `Model` class.

```python
# In backend/app/models.py
class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    display_name = Column(String, nullable=True)
    provider_id = Column(Integer, ForeignKey("providers.id"))
    pricing_input = Column(Float, default=0.0)
    pricing_output = Column(Float, default=0.0)
    context_window = Column(Integer, default=128000)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False) # ADDED
    capabilities = Column(JSON, nullable=True)

    provider = relationship("Provider", back_populates="models")
```

- [ ] **Step 2: Add SQLite Migration**
Modify `backend/app/database.py` to add the new column to existing databases on startup.

```python
# In backend/app/database.py, inside the init_db() function,
# where table migrations are handled (around line 100):

    if "models" in table_names:
        columns = await _sqlite_table_columns(conn, "models")
        # Add is_default migration if it doesn't exist
        migrations = {
            "is_default": "ALTER TABLE models ADD COLUMN is_default BOOLEAN DEFAULT 0"
        }
        for col, sql in migrations.items():
            if col not in columns:
                try:
                    await conn.execute(text(sql))
                except Exception as e:
                    print(f"Migration error ({col} in models): {e}")

```

- [ ] **Step 3: Commit**
```bash
git add backend/app/models.py backend/app/database.py
git commit -m "feat(db): add is_default column to models table with migration"
```

### Task 2: Backend API Schemas

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `frontend-v2/src/lib/types.ts`

- [ ] **Step 1: Update Pydantic Schemas**
Modify `backend/app/schemas.py` to include `is_default` in Model schemas.

```python
# In backend/app/schemas.py
class ModelCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    provider_id: int
    pricing_input: float = 0.0
    pricing_output: float = 0.0
    context_window: int = 128000
    is_active: bool = True
    is_default: bool = False # ADDED
    capabilities: Optional[dict] = None

class ModelUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    pricing_input: Optional[float] = None
    pricing_output: Optional[float] = None
    context_window: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None # ADDED
    capabilities: Optional[dict] = None

class ModelOut(BaseModel):
    id: int
    name: str
    display_name: Optional[str]
    provider_id: int
    pricing_input: float
    pricing_output: float
    context_window: int
    is_active: bool
    is_default: bool # ADDED
    capabilities: Optional[dict]

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Update Frontend Types**
Modify `frontend-v2/src/lib/types.ts` to reflect the new API schema.

```typescript
// In frontend-v2/src/lib/types.ts
export interface Model {
  id: number;
  name: string;
  display_name: string | null;
  provider_id: number;
  pricing_input: number;
  pricing_output: number;
  context_window: number;
  is_active: boolean;
  is_default: boolean; // ADDED
  capabilities: Record<string, unknown> | null;
}
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/schemas.py frontend-v2/src/lib/types.ts
git commit -m "feat(api): add is_default to Model schemas"
```

### Task 3: Backend API Logic

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Enforce Mutual Exclusivity on Create**
Modify the `POST /admin/models` route in `backend/app/admin_routes.py` to handle setting `is_default` and ensuring only one exists.

```python
# In backend/app/admin_routes.py - POST /admin/models
from sqlalchemy import update # Add if not imported

@router.post("/models", response_model=ModelOut)
async def create_model(data: ModelCreate, db: AsyncSession = Depends(get_session), auth=Depends(admin_auth)):
    result = await db.execute(select(Provider).where(Provider.id == data.provider_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider not found")
        
    # Prevent inactive default model
    if data.is_default and not data.is_active:
        raise HTTPException(status_code=400, detail="Default model must be active")

    model = DBModel(**data.model_dump())
    db.add(model)
    await db.flush() # Flush to get model.id
    
    # Ensure mutual exclusivity
    if model.is_default:
        await db.execute(
            update(DBModel)
            .where(DBModel.id != model.id)
            .values(is_default=False)
        )

    await db.commit()
    await db.refresh(model)
    return model
```

- [ ] **Step 2: Enforce Mutual Exclusivity on Update**
Modify the `PUT /admin/models/{model_id}` route in `backend/app/admin_routes.py`.

```python
# In backend/app/admin_routes.py - PUT /admin/models/{model_id}
@router.put("/models/{model_id}", response_model=ModelOut)
async def update_model(model_id: int, data: ModelUpdate, db: AsyncSession = Depends(get_session), auth=Depends(admin_auth)):
    result = await db.execute(select(DBModel).where(DBModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    update_data = data.model_dump(exclude_unset=True)
    
    # Check activity requirement if changing either field
    will_be_default = update_data.get("is_default", model.is_default)
    will_be_active = update_data.get("is_active", model.is_active)
    
    if will_be_default and not will_be_active:
         raise HTTPException(status_code=400, detail="Default model must be active")

    for key, value in update_data.items():
        setattr(model, key, value)

    # Ensure mutual exclusivity if setting as default
    if update_data.get("is_default") is True:
        await db.execute(
            update(DBModel)
            .where(DBModel.id != model.id)
            .values(is_default=False)
        )

    await db.commit()
    await db.refresh(model)
    return model
```

- [ ] **Step 3: Update Import CSV Logic (Optional but safe)**
In `backend/app/admin_routes.py`, within the `import_models_csv` function, if we don't want CSV imports modifying defaults automatically, we can strip or ignore it, but since `_coerce_imported_model_configs` doesn't include it, we don't strictly need to change it, but let's ensure it's safe by not allowing imported models to inadvertently become default unless handled explicitly. Since it's not in the import schema, it defaults to False on creation. No changes strictly needed, but verify.

- [ ] **Step 4: Commit**
```bash
git add backend/app/admin_routes.py
git commit -m "feat(api): enforce mutual exclusivity for default models"
```

### Task 4: Bot Fallback Logic

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update Bot Model Selection Logic**
Modify `cmd_start_convo` (around line 4100) and any generic model selection logic in `backend/app/bot.py` to check for `is_default` before falling back to the first available model.

```python
# In backend/app/bot.py - inside cmd_start_convo
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return
        
        # Determine model_id
        model_id = user.current_model_id
        if not model_id:
            # 1. Try to find the active default model
            default_model_result = await db.execute(
                select(DBModel.id)
                .join(Provider, Provider.id == DBModel.provider_id)
                .where(DBModel.is_active == True, Provider.is_active == True, DBModel.is_default == True)
            )
            model_id = default_model_result.scalar_one_or_none()
            
            # 2. Fallback to the first available active model if no default is found
            if not model_id:
                result = await db.execute(
                    select(DBModel)
                    .join(Provider, Provider.id == DBModel.provider_id)
                    .where(DBModel.is_active == True, Provider.is_active == True)
                    .order_by(Provider.name, DBModel.display_name, DBModel.name)
                )
                models = result.scalars().all()
                model_id = models[0].id if models else None

        project_for_chat = await _get_accessible_current_project(db, user)
```
*Note: Also search `backend/app/bot.py` for other places where a fallback model is needed (e.g., handling missing models in text generation if applicable).*

- [ ] **Step 2: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat(bot): use default model as fallback"
```

### Task 5: Frontend UI - Model Form & List

**Files:**
- Modify: `frontend-v2/src/components/config/ModelForm.tsx`
- Modify: `frontend-v2/src/components/config/ModelList.tsx`

- [ ] **Step 1: Update Model Form**
In `frontend-v2/src/components/config/ModelForm.tsx`, add the `is_default` state, checkbox, and update the mutation payload.

```typescript
// In frontend-v2/src/components/config/ModelForm.tsx

// Add state
const [isDefault, setIsDefault] = React.useState(false);

// Update useEffect
React.useEffect(() => {
    if (model) {
      // ... existing
      setIsDefault(model.is_default);
    } else {
      // ... existing
      setIsDefault(false);
    }
}, [model, isOpen, providers]);

// Update handleSubmit
const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isDefault && !isActive) {
        setError('A default model must be active.');
        return;
    }
    // ...
    mutation.mutate({
      name,
      display_name: displayName || null,
      provider_id: providerId,
      pricing_input: parseFloat(pricingInput),
      pricing_output: parseFloat(pricingOutput),
      context_window: parseInt(contextWindow),
      is_active: isActive,
      is_default: isDefault, // ADDED
      capabilities: { ... }
    });
};

// Add checkbox in JSX (near isActive checkbox)
<div className="flex items-center space-x-2">
  <input
    id="modelIsDefault"
    type="checkbox"
    checked={isDefault}
    onChange={(e) => setIsDefault(e.target.checked)}
    disabled={!isActive}
    className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary disabled:opacity-50"
  />
  <label htmlFor="modelIsDefault" className={`text-sm font-medium ${isActive ? 'text-muted-foreground' : 'text-muted-foreground/50'}`}>
    Set as default model
  </label>
</div>
```

- [ ] **Step 2: Update Model List**
In `frontend-v2/src/components/config/ModelList.tsx`, display a badge for the default model. Add the `Star` icon to imports.

```typescript
// In frontend-v2/src/components/config/ModelList.tsx
import { Edit2, Trash2, CheckCircle2, XCircle, Plus, Zap, Power, ImageIcon, Upload, Download, Star } from 'lucide-react'; // Added Star

// Inside the render loop for models:
// <div className="flex items-center space-x-2">
//   <span className="font-semibold">{model.display_name || model.name}</span>
  {model.is_default && (
    <span className="inline-flex items-center space-x-1 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 font-bold uppercase tracking-wider" title="Global Default Model">
      <Star className="w-3 h-3 fill-amber-600" />
      <span>Default</span>
    </span>
  )}
//   {model.is_active ? ...
```

- [ ] **Step 3: Commit**
```bash
git add frontend-v2/src/components/config/ModelForm.tsx frontend-v2/src/components/config/ModelList.tsx
git commit -m "feat(ui): add default model toggle and badge"
```
