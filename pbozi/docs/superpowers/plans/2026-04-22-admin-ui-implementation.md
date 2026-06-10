# JGPTi Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable, Sidebar-Centric Admin UI using Vite, React, and TanStack Query to control all JGPTi backend entities.

**Architecture:** A decentralized SPA that uses TanStack Query for background auto-polling and cache management, ensuring the UI remains responsive and never "locks" during data fetching.

**Tech Stack:** Vite, React, TypeScript, Tailwind CSS, Shadcn/UI, TanStack Query, Lucide React (icons).

---

### Task 1: Foundation & Scaffolding

**Files:**
- Create: `frontend-v2/package.json`
- Create: `frontend-v2/vite.config.ts`
- Create: `frontend-v2/tsconfig.json`
- Create: `frontend-v2/src/lib/api.ts`
- Create: `frontend-v2/src/lib/config.ts`

- [ ] **Step 1: Scaffold Vite project with dependencies**
Run: `mkdir frontend-v2 && cd frontend-v2 && npm init -y`
Add dependencies: `react`, `react-dom`, `lucide-react`, `@tanstack/react-query`, `axios`, `clsx`, `tailwind-merge`
Add dev dependencies: `vite`, `@vitejs/plugin-react`, `typescript`, `tailwindcss`, `postcss`, `autoprefixer`

- [ ] **Step 2: Create dynamic API configuration**
File: `frontend-v2/src/lib/config.ts`
```typescript
export const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (typeof window !== "undefined") {
    return `http://${window.location.hostname}:8000/api`;
  }
  return "http://localhost:8000/api";
};
export const API_URL = getApiUrl();
```

- [ ] **Step 3: Implement unified API client**
File: `frontend-v2/src/lib/api.ts`
Include basic fetch wrapper with Bearer token injection from `localStorage`.

- [ ] **Step 4: Commit**
```bash
git add frontend-v2/
git commit -m "chore: scaffold vite project and api foundation"
```

---

### Task 2: Layout & Navigation (The Shell)

**Files:**
- Create: `frontend-v2/src/components/layout/Sidebar.tsx`
- Create: `frontend-v2/src/components/layout/Header.tsx`
- Create: `frontend-v2/src/App.tsx`

- [ ] **Step 1: Create Sidebar component**
Implement the Sidebar-Centric design with sections: Dashboard, Config, Intelligence, Users, Monitoring.

- [ ] **Step 2: Create QueryClientProvider wrapper**
Wrap `App.tsx` with `QueryClientProvider` from TanStack Query.

- [ ] **Step 3: Implement Theme Toggle logic**
Add a basic theme switcher (Dark/Light/System) using a `ThemeContext`.

- [ ] **Step 4: Commit**
```bash
git commit -m "feat: add sidebar layout and theme provider"
```

---

### Task 3: Dashboard & Stats (Real-time Overview)

**Files:**
- Create: `frontend-v2/src/pages/Dashboard.tsx`
- Create: `frontend-v2/src/hooks/useStats.ts`

- [ ] **Step 1: Create useStats hook with auto-polling**
Use `useQuery` with `refetchInterval: 30000`.

- [ ] **Step 2: Implement Dashboard stats cards**
Render cards for Providers, Models, Projects, Chats, and Users.

- [ ] **Step 3: Commit**
```bash
git commit -m "feat: implement dashboard with 30s auto-polling stats"
```

---

### Task 4: User & Wallet Management

**Files:**
- Create: `frontend-v2/src/pages/Users.tsx`
- Create: `frontend-v2/src/components/users/UserTable.tsx`
- Create: `frontend-v2/src/components/users/CreditAdjustmentModal.tsx`

- [ ] **Step 1: Implement User Table with pagination/search**
Use TanStack Table (or simple mapping) to display user list from `/admin/users`.

- [ ] **Step 2: Implement Credit Adjustment Modal**
Form to POST to `/admin/users/{id}/credit-adjustments`.

- [ ] **Step 3: Commit**
```bash
git commit -m "feat: add user management and credit adjustment tools"
```

---

### Task 5: AI Configuration (Providers & Models)

**Files:**
- Create: `frontend-v2/src/pages/Config.tsx`
- Create: `frontend-v2/src/components/config/ProviderForm.tsx`
- Create: `frontend-v2/src/components/config/ModelForm.tsx`

- [ ] **Step 1: Build Provider CRUD UI**
List and edit providers.

- [ ] **Step 2: Build Model CRUD UI**
Configure pricing and context windows for models.

- [ ] **Step 3: Commit**
```bash
git commit -m "feat: implement provider and model configuration"
```

---

### Task 6: Monitoring & Audit Logs

**Files:**
- Create: `frontend-v2/src/pages/Monitoring.tsx`
- Create: `frontend-v2/src/components/monitoring/UsageFeed.tsx`
- Create: `frontend-v2/src/components/monitoring/AuditLog.tsx`

- [ ] **Step 1: Implement Live Usage Feed**
Polling `/admin/usage-events` to show token usage.

- [ ] **Step 2: Implement Admin Action Audit Log**
View `/admin/admin-actions`.

- [ ] **Step 3: Commit**
```bash
git commit -m "feat: add monitoring feeds and audit logs"
```

---

### Task 7: Cleanup & Verification

- [ ] **Step 1: Final verification of all Admin endpoints**
Ensure all routes from `BACKEND_API.md` are covered.
- [ ] **Step 2: Final Build check**
Run `npm run build` in `frontend-v2`.
- [ ] **Step 3: Commit**
```bash
git commit -m "chore: final verification and build check"
```
