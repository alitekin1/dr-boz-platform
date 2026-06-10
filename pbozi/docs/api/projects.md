# Projects & Documents API

Manages user projects and the knowledge base (RAG).

## Projects

### 1. List Projects
Returns projects visible to the user.
- **URL:** `GET /projects`
- **Query Params:** `telegram_user_id` (optional), `root_only` (boolean)

### 2. Create Project
- **URL:** `POST /projects`
- **Body:**
  ```json
  {
    "name": "My New Project",
    "description": "Optional description",
    "instructions": "Custom system prompt additions"
  }
  ```

### 3. Share Project
Generates a share token and Telegram deep-link.
- **URL:** `POST /projects/{project_id}/share`
- **Query Params:** `bot_username` (optional)

## Documents (Knowledge Base)

### 1. Upload Document
Uploads a file and triggers background RAG indexing.
- **URL:** `POST /projects/{project_id}/documents/upload`
- **Multipart Form:** `file` (Supported: PDF, TXT, MD, CSV, DOCX, XLSX, JPG, PNG)

### 2. Upload Document (Base64)
Useful for Telegram bot file uploads.
- **URL:** `POST /projects/{project_id}/documents/upload-base64`
- **Body:**
  ```json
  {
    "filename": "notes.txt",
    "content": "<base64_string>",
    "file_type": "txt"
  }
  ```

### 3. List Documents
- **URL:** `GET /projects/{project_id}/documents`

### 4. Delete Document
- **URL:** `DELETE /projects/{project_id}/documents/{document_id}`
