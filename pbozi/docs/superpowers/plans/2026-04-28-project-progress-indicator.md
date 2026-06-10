# Project Progress Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a "Projects" management page in the frontend-v2 with a progress indicator for batch document uploads.

**Architecture:** Add a new "Projects" page to the React frontend. Use TanStack Query for data fetching and local state to track batch upload progress.

**Tech Stack:** React, TypeScript, TanStack Query, Axios, Tailwind CSS.

---

### Task 0: Backend - Delete Document Endpoint

**Files:**
- Modify: `backend/app/main_routes.py`

- [ ] **Step 1: Add delete_document endpoint**
    Add `@router.delete("/projects/{project_id}/documents/{document_id}")` to `backend/app/main_routes.py`.

- [ ] **Step 2: Commit**
```bash
git add backend/app/main_routes.py
git commit -m "feat: add delete document endpoint"
```

---

### Task 1: Update Types and API Client

**Files:**
- Modify: `frontend-v2/src/lib/types.ts`
- Modify: `frontend-v2/src/lib/api.ts`

- [ ] **Step 1: Add Project and Document interfaces**
    Update `frontend-v2/src/lib/types.ts` to include `Project` and `Document` interfaces.

- [ ] **Step 2: Add API helpers for projects and documents**
    Update `frontend-v2/src/lib/api.ts` to include `createProject`, `deleteProject`, `getDocuments`, `uploadDocument`, and `deleteDocument`.

- [ ] **Step 3: Commit**
```bash
git add frontend-v2/src/lib/types.ts frontend-v2/src/lib/api.ts
git commit -m "feat: add project and document types and api helpers"
```

---

### Task 2: Update Layout and Navigation

**Files:**
- Modify: `frontend-v2/src/components/layout/Sidebar.tsx`
- Modify: `frontend-v2/src/App.tsx`

- [ ] **Step 1: Add "Projects" to Sidebar**
    Update `navItems` in `Sidebar.tsx`.

- [ ] **Step 2: Register Projects page in App.tsx**
    Update `renderContent` to handle the 'Projects' section.

- [ ] **Step 3: Commit**
```bash
git add frontend-v2/src/components/layout/Sidebar.tsx frontend-v2/src/App.tsx
git commit -m "feat: add projects section to navigation"
```

---

### Task 4: Implement Projects Page

**Files:**
- Create: `frontend-v2/src/pages/Projects.tsx`

- [ ] **Step 1: Create Projects.tsx with Batch Upload Logic**
    Implement the project list, project selection, and the document upload loop with progress indicator.

- [ ] **Step 2: Verify the progress indicator**
    Run the frontend and test uploading multiple files to a project.

- [ ] **Step 3: Commit**
```bash
git add frontend-v2/src/pages/Projects.tsx
git commit -m "feat: implement projects page with batch upload progress"
```
