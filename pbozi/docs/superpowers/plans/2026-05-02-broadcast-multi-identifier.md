# Broadcast Multi-Identifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `broadcast_message` endpoint to support targeting users by internal ID, Telegram ID, or phone number.

**Architecture:** Update the SQLAlchemy query in `broadcast_message` to use `or_` with categorized identifiers (numeric vs strings).

**Tech Stack:** FastAPI, SQLAlchemy, httpx.

---

### Task 1: Create Verification Script

**Files:**
- Create: `backend/app/test_broadcast_query.py`

- [ ] **Step 1: Write the verification script**

```python
import asyncio
import json
from sqlalchemy import select, or_
from app.models import UserPreference

async def test_identifier_resolution():
    # Mock identifiers
    target_user_ids = json.dumps([1, "123456789", "+989123456789", "invalid"])
    
    # Logic to test
    identifiers = json.loads(target_user_ids)
    id_list = []
    phone_list = []
    for val in identifiers:
        if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
            id_list.append(int(val))
        if isinstance(val, str):
            phone_list.append(val)
            
    print(f"ID List: {id_list}")
    print(f"Phone List: {phone_list}")
    
    query = select(UserPreference).where(UserPreference.telegram_user_id.is_not(None))
    if identifiers:
        query = query.where(
            or_(
                UserPreference.id.in_(id_list),
                UserPreference.telegram_user_id.in_(id_list),
                UserPreference.phone_number.in_(phone_list)
            )
        )
    
    # Check query construction (manual inspection of print output if needed)
    print(f"Generated Query: {query}")

if __name__ == "__main__":
    asyncio.run(test_identifier_resolution())
```

- [ ] **Step 2: Run verification script (initial)**

Run: `python3 backend/app/test_broadcast_query.py`
Expected: Should print ID List, Phone List and Query.

- [ ] **Step 3: Commit**

```bash
git add backend/app/test_broadcast_query.py
git commit -m "test: add verification script for broadcast identifier resolution"
```

---

### Task 2: Refactor `broadcast_message`

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Apply refactor to `broadcast_message`**

```python
@router.post("/broadcast", response_model=BroadcastOut)
async def broadcast_message(
    message: str = Form(...),
    target_user_ids: Optional[str] = Form(None), # This will now be treated as target_identifiers
    target_groups: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    from app.config import BOT_TOKEN, BALE_API_BASE_URL
    import json
    from sqlalchemy import or_

    # Parse JSON strings if provided
    try:
        # We treat target_user_ids as a list of identifiers (can be ID, Telegram ID, or Phone)
        identifiers = json.loads(target_user_ids) if target_user_ids else None
    except:
        identifiers = None
        
    try:
        groups = json.loads(target_groups) if target_groups else None
    except:
        groups = None

    # 1. Identify target users
    query = select(UserPreference).where(UserPreference.telegram_user_id.is_not(None))
    
    if identifiers:
        # Resolve identifiers: can be internal ID, telegram_user_id, or phone_number
        id_list = []
        phone_list = []
        for val in identifiers:
            if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
                id_list.append(int(val))
            if isinstance(val, str):
                phone_list.append(val)
        
        query = query.where(
            or_(
                UserPreference.id.in_(id_list),
                UserPreference.telegram_user_id.in_(id_list),
                UserPreference.phone_number.in_(phone_list)
            )
        )
    
    if groups:
        query = query.where(UserPreference.account_status.in_(groups))
        
    result = await db.execute(query)
    users = result.scalars().all()
    
    # ... (rest of the code remains the same)
```

- [ ] **Step 2: Verify imports**

Ensure `or_` is imported at the top of the file or locally within the function if preferred (though top-level is better). The provided snippet uses local import.

- [ ] **Step 3: Commit**

```bash
git add backend/app/admin_routes.py
git commit -m "feat: support multi-identifier resolution in broadcast_message"
```

---

### Task 3: Final Verification

- [ ] **Step 1: Run verification script again**

Run: `python3 backend/app/test_broadcast_query.py`
Expected: Success.

- [ ] **Step 2: Remove verification script**

Run: `rm backend/app/test_broadcast_query.py`

- [ ] **Step 3: Commit final changes**

```bash
git add backend/app/admin_routes.py
git commit -m "chore: cleanup verification script"
```
