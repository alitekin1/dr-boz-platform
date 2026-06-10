# AI Model CSV Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a CSV import feature for AI models in the admin panel to allow bulk creation.

**Architecture:**
- **Backend:** New FastAPI endpoint `/admin/models/import-csv` that accepts a CSV file, parses it, and creates models tied to existing providers.
- **Frontend:** "Import CSV" button in `ModelList` component, standard file upload logic, and result reporting.

**Tech Stack:** FastAPI (Python), React (TypeScript), TanStack Query, Axios, SQLAlchemy.

---

### Task 1: Backend Implementation

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Add necessary imports**
  Add `UploadFile`, `File` from `fastapi`, and `csv`, `io`.

- [ ] **Step 2: Implement `/models/import-csv` endpoint**
  ```python
  from fastapi import UploadFile, File
  import csv
  import io

  @router.post("/models/import-csv")
  async def import_models_csv(
      file: UploadFile = File(...),
      db: AsyncSession = Depends(get_session),
      _=Depends(verify_admin)
  ):
      content = await file.read()
      stream = io.StringIO(content.decode("utf-8"))
      reader = csv.DictReader(stream)
      
      results = {"success": 0, "failed": 0, "errors": []}
      
      for row_idx, row in enumerate(reader, start=1):
          try:
              provider_name = row.get("provider_name")
              if not provider_name:
                  raise ValueError("Missing provider_name")
              
              # Find provider
              p_stmt = select(Provider).where(func.lower(Provider.name) == provider_name.lower())
              p_res = await db.execute(p_stmt)
              provider = p_res.scalar_one_or_none()
              
              if not provider:
                  raise ValueError(f"Provider '{provider_name}' not found")
              
              # Prepare model data
              model_data = {
                  "name": row["name"],
                  "display_name": row.get("display_name"),
                  "provider_id": provider.id,
                  "pricing_input": float(row.get("pricing_input", 0)),
                  "pricing_output": float(row.get("pricing_output", 0)),
                  "context_window": int(row.get("context_window", 128000)),
                  "is_active": row.get("is_active", "true").lower() == "true",
                  "capabilities": {"image_input": row.get("supports_image_input", "false").lower() == "true"}
              }
              
              model = DBModel(**model_data)
              db.add(model)
              results["success"] += 1
          except Exception as e:
              results["failed"] += 1
              results["errors"].append(f"Row {row_idx}: {str(e)}")
      
      await db.commit()
      return results
  ```

- [ ] **Step 3: Verify backend with a curl command (once running)**
  `curl -X POST -F "file=@models.csv" http://localhost:8000/admin/models/import-csv -H "Authorization: Bearer <token>"`

---

### Task 2: Frontend API Integration

**Files:**
- Modify: `frontend-v2/src/lib/api.ts`

- [ ] **Step 1: Add `importModelsCSV` function**
  ```typescript
  export const importModelsCSV = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/admin/models/import-csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  };
  ```

---

### Task 3: Frontend UI Components

**Files:**
- Modify: `frontend-v2/src/components/config/ModelList.tsx`

- [ ] **Step 1: Add "Import CSV" button and hidden file input**
  Add a button next to "Add Model" and a `useRef` for the file input.

- [ ] **Step 2: Implement `handleFileChange` and `handleImport`**
  Use `useMutation` to call `importModelsCSV` and invalidate `models` query on success. Show an alert with the results.

---

### Task 4: Final Verification

- [ ] **Step 1: Create a test CSV**
  ```csv
  provider_name,name,display_name,pricing_input,pricing_output,context_window,is_active,supports_image_input
  OpenAI,gpt-4o,GPT-4o,0.005,0.015,128000,true,true
  Anthropic,claude-3-5-sonnet,Claude 3.5 Sonnet,0.003,0.009,200000,true,true
  ```

- [ ] **Step 2: Perform the import via UI and verify models appear in list**
