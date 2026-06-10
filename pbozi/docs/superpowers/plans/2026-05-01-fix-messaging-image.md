# Fix Messaging and Add Image-with-Caption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the messaging broadcast failure by correctly mapping user IDs to Telegram IDs and add support for sending images with captions using Bale's `sendPhoto` API.

**Architecture:** 
- Transition `/api/admin/broadcast` to support `multipart/form-data`.
- Update backend logic to fetch `telegram_user_id` for targeted users.
- Use `sendPhoto` when an image is uploaded, fallback to `sendMessage`.
- Enhance frontend UI with an image picker and preview.

**Tech Stack:** FastAPI, httpx, React, Axios, Tailwind CSS.

---

### Task 1: Backend API Refactor

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Update imports in `backend/app/admin_routes.py`**
    Add `Form` and `Optional` to imports.
    ```python
    from fastapi import APIRouter, Depends, HTTPException, Query, Security, UploadFile, File, Form
    from typing import Optional, List
    import json
    ```

- [ ] **Step 2: Refactor `broadcast_message` endpoint**
    Change the function signature to accept `Form` parameters and an optional `File`.
    Update logic to use `telegram_user_id` and handle `sendPhoto`.
    
    ```python
    @router.post("/broadcast", response_model=BroadcastOut)
    async def broadcast_message(
        message: str = Form(...),
        target_user_ids: Optional[str] = Form(None), # JSON string of list
        target_groups: Optional[str] = Form(None),   # JSON string of list
        photo: Optional[UploadFile] = File(None),
        db: AsyncSession = Depends(get_session),
        _=Depends(verify_admin)
    ):
        from app.config import BOT_TOKEN, BALE_API_BASE_URL
        
        # Parse JSON strings if provided
        user_ids = json.loads(target_user_ids) if target_user_ids else None
        groups = json.loads(target_groups) if target_groups else None

        # 1. Identify target users
        query = select(UserPreference).where(UserPreference.telegram_user_id.is_not(None))
        
        if user_ids:
            query = query.where(UserPreference.id.in_(user_ids))
        
        if groups:
            query = query.where(UserPreference.account_status.in_(groups))
            
        result = await db.execute(query)
        users = result.scalars().all()
        
        if not users:
            return BroadcastOut(success_count=0, failure_count=0, total_targeted=0)

        # 2. Prepare for sending
        success_count = 0
        failure_count = 0
        errors = []
        
        base_url = f"{BALE_API_BASE_URL.rstrip('/')}/bot{BOT_TOKEN}"
        
        # Read photo content if provided
        photo_content = None
        photo_filename = None
        if photo:
            photo_content = await photo.read()
            photo_filename = photo.filename
            url = f"{base_url}/sendPhoto"
        else:
            url = f"{base_url}/sendMessage"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for user in users:
                try:
                    if photo_content:
                        files = {"photo": (photo_filename, photo_content)}
                        data = {
                            "chat_id": user.telegram_user_id,
                            "caption": message,
                        }
                        resp = await client.post(url, data=data, files=files)
                    else:
                        payload = {
                            "chat_id": user.telegram_user_id,
                            "text": message,
                        }
                        resp = await client.post(url, json=payload)
                        
                    if resp.status_code == 200:
                        success_count += 1
                    else:
                        failure_count += 1
                        errors.append({
                            "user_id": user.id,
                            "telegram_id": user.telegram_user_id,
                            "status_code": resp.status_code,
                            "response": resp.json() if resp.headers.get("content-type") == "application/json" else resp.text[:200]
                        })
                except Exception as e:
                    failure_count += 1
                    errors.append({
                        "user_id": user.id,
                        "error": str(e)
                    })
                    
        return BroadcastOut(
            success_count=success_count,
            failure_count=failure_count,
            total_targeted=len(users),
            errors=errors if errors else None
        )
    ```

- [ ] **Step 3: Commit Backend changes**
    ```bash
    git add backend/app/admin_routes.py
    git commit -m "fix(backend): fix broadcast user mapping and add sendPhoto support"
    ```

---

### Task 2: Frontend API Update

**Files:**
- Modify: `frontend-v2/src/lib/api.ts`

- [ ] **Step 1: Update `broadcastMessage` helper**
    Change it to accept a `File` and use `FormData`.
    ```typescript
    export const broadcastMessage = (data: { 
      message: string, 
      target_user_ids?: number[], 
      target_groups?: string[],
      photo?: File | null
    }) => {
      const formData = new FormData();
      formData.append('message', data.message);
      if (data.target_user_ids) formData.append('target_user_ids', JSON.stringify(data.target_user_ids));
      if (data.target_groups) formData.append('target_groups', JSON.stringify(data.target_groups));
      if (data.photo) formData.append('photo', data.photo);
      
      return api.post("/admin/broadcast", formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      }).then((r) => r.data);
    };
    ```

- [ ] **Step 2: Commit Frontend API changes**
    ```bash
    git add frontend-v2/src/lib/api.ts
    git commit -m "feat(frontend): update broadcastMessage API to support multipart/form-data"
    ```

---

### Task 3: Frontend UI Enhancement

**Files:**
- Modify: `frontend-v2/src/pages/Messaging.tsx`

- [ ] **Step 1: Update `Messaging` component state and handlers**
    Add `photo` state and `handlePhotoChange`.
    ```typescript
    const [photo, setPhoto] = useState<File | null>(null);
    const [photoPreview, setPhotoPreview] = useState<string | null>(null);

    const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setPhoto(file);
        const reader = new FileReader();
        reader.onloadend = () => setPhotoPreview(reader.result as string);
        reader.readAsDataURL(file);
      }
    };
    ```

- [ ] **Step 2: Add Image picker and preview UI**
    Add the file input and preview display above or below the message textarea.
    
- [ ] **Step 3: Update `handleSend` call**
    Pass the `photo` to `broadcastMessage`.
    ```typescript
    const data = await broadcastMessage({
      message: message.trim(),
      target_groups: targetType === "all" || targetType === "individual" ? undefined : [targetType],
      target_user_ids: targetType === "individual" ? [parseInt(targetUserId)] : undefined,
      photo: photo,
    });
    ```

- [ ] **Step 4: Commit UI changes**
    ```bash
    git add frontend-v2/src/pages/Messaging.tsx
    git commit -m "feat(frontend): add image upload and preview to messaging page"
    ```

---

### Task 4: Verification

- [ ] **Step 1: Check backend compilation/linting**
- [ ] **Step 2: Check frontend compilation**
- [ ] **Step 3: Final sanity check of the code**
