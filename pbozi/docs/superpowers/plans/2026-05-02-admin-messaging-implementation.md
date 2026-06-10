# Admin Messaging and User List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve admin user management and messaging by adding phone number visibility/search and resolving various identifiers (Phone, Telegram ID) during messaging.

**Architecture:** 
- Frontend: Enhance `UserTable` and `Users` pages with phone columns and search. Use URL search params to pass user info from User List to Messaging page.
- Backend: Refactor `broadcast_message` in `admin_routes.py` to resolve multiple identifier types to `telegram_user_id`.

**Tech Stack:** React (TypeScript), FastAPI (Python), SQLAlchemy, Tailwind CSS.

---

### Task 1: Backend Identifier Resolution

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Refactor `broadcast_message` to support identifier resolution**

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
    from sqlalchemy import or_, cast, String

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
        # Convert identifiers to strings for phone comparison and integers for ID comparison
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
    # ... (rest of the logic remains similar but uses user.telegram_user_id for sending)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/admin_routes.py
git commit -m "backend: enhance broadcast messaging with identifier resolution"
```

### Task 2: Frontend User List UI (Phone Column)

**Files:**
- Modify: `frontend-v2/src/components/users/UserTable.tsx`

- [ ] **Step 1: Add Phone Number column and Message button**

```tsx
// Inside UserTable component
<thead className="text-xs uppercase bg-muted/50 text-muted-foreground border-y border-border">
  <tr>
    <th className="px-6 py-4 font-medium">User</th>
    <th className="px-6 py-4 font-medium">Phone</th> {/* New Column */}
    <th className="px-6 py-4 font-medium">Status</th>
    {/* ... */}
  </tr>
</thead>
// ...
<td className="px-6 py-4 font-mono">
  {user.phone_number || '-'}
</td>
// ...
// Add Message button in Actions
<button
  onClick={() => window.location.href = `/messaging?userId=${user.telegram_user_id || user.id}`}
  className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted transition-colors"
>
  <Send className="w-3.5 h-3.5" />
  Message
</button>
```

- [ ] **Step 2: Commit**

```bash
git add frontend-v2/src/components/users/UserTable.tsx
git commit -m "frontend: add phone column and message button to user table"
```

### Task 3: Frontend User Search Enhancement

**Files:**
- Modify: `frontend-v2/src/pages/Users.tsx`

- [ ] **Step 1: Update search filter to include phone number**

```tsx
const filteredUsers = safeUsers.filter((user) => {
    const search = searchQuery.toLowerCase();
    const telegramUserId = String(user?.telegram_user_id ?? '');
    const username = String(user?.username ?? '').toLowerCase();
    const firstName = String(user?.first_name ?? '').toLowerCase();
    const preferredName = String(user?.preferred_name ?? '').toLowerCase();
    const phoneNumber = String(user?.phone_number ?? '').toLowerCase(); // New
    return (
      telegramUserId.includes(search) ||
      username.includes(search) ||
      firstName.includes(search) ||
      preferredName.includes(search) ||
      phoneNumber.includes(search) // New
    );
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend-v2/src/pages/Users.tsx
git commit -m "frontend: enhance user search to include phone number"
```

### Task 4: Frontend Messaging Page Integration

**Files:**
- Modify: `frontend-v2/src/pages/Messaging.tsx`

- [ ] **Step 1: Handle `userId` query parameter**

```tsx
import { useSearchParams } from "react-router-dom";
// ...
const [searchParams] = useSearchParams();
// ...
useEffect(() => {
  const userId = searchParams.get("userId");
  if (userId) {
    setTargetType("individual");
    setTargetUserId(userId);
  }
}, [searchParams]);
```

- [ ] **Step 2: Commit**

```bash
git add frontend-v2/src/pages/Messaging.tsx
git commit -m "frontend: integrate messaging page with user list via query params"
```
