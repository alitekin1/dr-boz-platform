# AI Model CSV Import Design

This document outlines the design for adding a CSV import feature to the AI Model management section of the Admin UI.

## 1. Goal
Provide an efficient way for administrators to bulk-import AI model configurations from a CSV file.

## 2. Architecture

### Backend Changes
- **File: `backend/app/admin_routes.py`**
  - New Endpoint: `POST /models/import-csv`
  - Input: `multipart/form-data` with a `file` field.
  - Logic:
    1. Parse CSV using standard `csv` library.
    2. Headers: `provider_name`, `name`, `display_name`, `pricing_input`, `pricing_output`, `context_window`, `is_active`, `supports_image_input`.
    3. For each row:
       - Find `Provider` by name (case-insensitive).
       - Skip/Error if provider not found.
       - Validate data types (pricing, context window).
       - Create `Model` object (checking for existing name+provider_id to avoid duplicates if possible, or just create new).
    4. Return summary report.

### Frontend Changes
- **File: `frontend-v2/src/components/config/ModelList.tsx`**
  - Add "Import CSV" button.
  - Implement `handleImportCSV` using a hidden file input.
  - Send file to backend using `axios`.
  - Invalidate `models` query on success.
- **File: `frontend-v2/src/lib/api.ts`**
  - Add `importModelsCSV(file: File)` helper.

## 3. Data Flow
1. Admin selects CSV.
2. Frontend sends `FormData` to `/models/import-csv`.
3. Backend processes, commits to DB, and returns JSON report.
4. Frontend displays success/error notification.

## 4. Error Handling
- Invalid CSV format: Return 400 with error details.
- Missing Provider: Report specific rows that failed in the response.
- Database Errors: Atomic transaction per row (or bulk if preferred).

## 5. Verification Plan
- Manual test: Upload a sample CSV with valid and invalid (missing provider) data.
- Automated test (optional): Add a pytest case for the new endpoint.
