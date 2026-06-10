# Admin Error Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture user-facing and system errors and display them in the Admin Panel's Monitoring page.

**Architecture:** A new `ErrorLog` SQLAlchemy model will store error details. Global exception handlers in FastAPI and Telegram bot will catch 500s and log them. New admin API routes will serve these logs to a new `ErrorLogTable` React component in the Monitoring page.

**Tech Stack:** Python, FastAPI, SQLAlchemy, React, Tailwind CSS.

---

### Task 1: Create Database Model

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Test: `test_error_model.py` (New)

- [ ] **Step 1: Write the failing test**
Create `test_error_model.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import Base, ErrorLog
from datetime import datetime

engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def test_error_log_creation():
    db = TestingSessionLocal()
    error = ErrorLog(
        source="API",
        error_message="Test Error",
        stack_trace="Traceback...",
        user_id=1,
        resolved=False
    )
    db.add(error)
    db.commit()
    db.refresh(error)
    
    assert error.id is not None
    assert error.source == "API"
    assert error.resolved is False
    assert type(error.timestamp) is datetime
```

- [ ] **Step 2: Run test to verify it fails**
Run: `python -m pytest test_error_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'ErrorLog' from 'backend.app.models'`

- [ ] **Step 3: Write minimal implementation**
In `backend/app/models.py`, add:
```python
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from datetime import datetime

class ErrorLog(Base):
    __tablename__ = "error_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    source = Column(String)
    error_message = Column(Text)
    stack_trace = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved = Column(Boolean, default=False)
```

In `backend/app/schemas.py`, add:
```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ErrorLogBase(BaseModel):
    source: str
    error_message: str
    stack_trace: str
    user_id: Optional[int] = None
    resolved: bool = False

class ErrorLogResponse(ErrorLogBase):
    id: int
    timestamp: datetime

    class Config:
        orm_mode = True
```

- [ ] **Step 4: Run test to verify it passes**
Run: `python -m pytest test_error_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
Run: `git add test_error_model.py backend/app/models.py backend/app/schemas.py && git commit -m "feat: add ErrorLog database model and schemas"`

### Task 2: Implement Admin API Routes

**Files:**
- Modify: `backend/app/admin_routes.py`
- Test: `test_error_routes.py` (New)

- [ ] **Step 1: Write the failing test**
Create `test_error_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_get_errors_unauthorized():
    response = client.get("/admin/errors")
    assert response.status_code == 401

```

- [ ] **Step 2: Write minimal implementation**
In `backend/app/admin_routes.py`, add the endpoints:
```python
from .schemas import ErrorLogResponse
from .models import ErrorLog
from sqlalchemy import desc

@router.get("/errors", response_model=list[ErrorLogResponse])
def get_error_logs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    errors = db.query(ErrorLog).order_by(desc(ErrorLog.timestamp)).offset(skip).limit(limit).all()
    return errors

@router.patch("/errors/{error_id}/resolve")
def resolve_error_log(error_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    error_log = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
    if not error_log:
        raise HTTPException(status_code=404, detail="Error log not found")
    error_log.resolved = True
    db.commit()
    return {"status": "success"}
```

- [ ] **Step 3: Commit**
Run: `git add backend/app/admin_routes.py test_error_routes.py && git commit -m "feat: add admin routes for fetching and resolving error logs"`

### Task 4: Add Global Exception Handlers

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Write minimal implementation for FastAPI**
In `backend/app/main.py`, add:
```python
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback
from .models import ErrorLog
from .database import SessionLocal

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    db = SessionLocal()
    try:
        error_log = ErrorLog(
            source="API",
            error_message=str(exc),
            stack_trace=traceback.format_exc()
        )
        db.add(error_log)
        db.commit()
    except Exception as e:
        import logging
        logging.error(f"Failed to save error log: {e}")
    finally:
        db.close()
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )
```

- [ ] **Step 2: Write minimal implementation for Telegram Bot**
In `backend/app/bot.py`, add:
```python
import traceback
from .database import SessionLocal
from .models import ErrorLog
import logging

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"Exception while handling an update: {context.error}")
    db = SessionLocal()
    try:
        user_id = None
        if update and hasattr(update, 'effective_user') and update.effective_user:
            user_id = update.effective_user.id
            
        error_log = ErrorLog(
            source="Telegram",
            error_message=str(context.error),
            stack_trace=traceback.format_exc(),
            user_id=user_id
        )
        db.add(error_log)
        db.commit()
    except Exception as e:
        logging.error(f"Failed to log Telegram error: {e}")
    finally:
        db.close()

# application.add_error_handler(error_handler)
```

- [ ] **Step 3: Commit**
Run: `git add backend/app/main.py backend/app/bot.py && git commit -m "feat: add global exception handlers for API and Telegram bot"`

### Task 5: Frontend API Integration

**Files:**
- Modify: `frontend-v2/src/lib/api.ts`
- Modify: `frontend-v2/src/lib/types.ts`

- [ ] **Step 1: Add types**
In `frontend-v2/src/lib/types.ts`, add:
```typescript
export interface ErrorLog {
  id: number;
  timestamp: string;
  source: string;
  error_message: string;
  stack_trace: string;
  user_id: number | null;
  resolved: boolean;
}
```

- [ ] **Step 2: Add API methods**
In `frontend-v2/src/lib/api.ts`, add to the `api` object:
```typescript
  getErrors: async (skip = 0, limit = 50): Promise<ErrorLog[]> => {
    const res = await fetch(`/admin/errors?skip=${skip}&limit=${limit}`, {
      headers: getAuthHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch errors');
    return res.json();
  },
  resolveError: async (id: number): Promise<void> => {
    const res = await fetch(`/admin/errors/${id}/resolve`, {
      method: 'PATCH',
      headers: getAuthHeaders()
    });
    if (!res.ok) throw new Error('Failed to resolve error');
  },
```

- [ ] **Step 3: Commit**
Run: `git add frontend-v2/src/lib/api.ts frontend-v2/src/lib/types.ts && git commit -m "feat: add frontend types and API methods for error logs"`

### Task 6: Frontend ErrorLog Component

**Files:**
- Create: `frontend-v2/src/components/monitoring/ErrorLogTable.tsx`
- Modify: `frontend-v2/src/pages/Monitoring.tsx`

- [ ] **Step 1: Create Component**
Create `frontend-v2/src/components/monitoring/ErrorLogTable.tsx`:
```tsx
import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { ErrorLog } from '../../lib/types';

export const ErrorLogTable: React.FC = () => {
  const [errors, setErrors] = useState<ErrorLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);

  const fetchErrors = async () => {
    try {
      const data = await api.getErrors();
      setErrors(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchErrors();
    const interval = setInterval(fetchErrors, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleResolve = async (id: number) => {
    await api.resolveError(id);
    fetchErrors();
  };

  if (loading) return <div>Loading errors...</div>;

  return (
    <div className="bg-card border rounded-xl shadow-sm overflow-hidden">
      <div className="p-4 border-b bg-muted/30">
        <h3 className="font-semibold text-destructive">Error Logs</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground bg-muted/50">
            <tr>
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Message</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {errors.map((error) => (
              <tr key={error.id} className="border-b">
                <td className="px-4 py-3">{new Date(error.timestamp).toLocaleString()}</td>
                <td className="px-4 py-3">{error.source}</td>
                <td className="px-4 py-3 truncate max-w-xs" title={error.error_message}>{error.error_message}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded-full text-xs ${error.resolved ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                    {error.resolved ? 'Resolved' : 'Active'}
                  </span>
                </td>
                <td className="px-4 py-3 space-x-2">
                  <button onClick={() => setSelectedTrace(error.stack_trace)} className="text-blue-600 hover:underline">Trace</button>
                  {!error.resolved && (
                    <button onClick={() => handleResolve(error.id)} className="text-emerald-600 hover:underline">Resolve</button>
                  )}
                </td>
              </tr>
            ))}
            {errors.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-4 text-muted-foreground">No errors found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedTrace && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-background p-6 rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-semibold text-lg">Stack Trace</h3>
              <button onClick={() => setSelectedTrace(null)} className="text-muted-foreground hover:text-foreground">Close</button>
            </div>
            <pre className="bg-muted p-4 rounded overflow-auto flex-1 text-xs">{selectedTrace}</pre>
          </div>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Add to Monitoring Page**
In `frontend-v2/src/pages/Monitoring.tsx`, add the import and add the section:
```tsx
import { ErrorLogTable } from '../components/monitoring/ErrorLogTable';

// inside the grid layout, add:
<section id="error-logs" className="mt-8">
  <ErrorLogTable />
</section>
```

- [ ] **Step 3: Commit**
Run: `git add frontend-v2/src/components/monitoring/ErrorLogTable.tsx frontend-v2/src/pages/Monitoring.tsx && git commit -m "feat: add ErrorLogTable to Admin Monitoring page"`
