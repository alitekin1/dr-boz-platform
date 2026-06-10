# User Table Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update UserTable to include Phone column and Message action.

**Architecture:** Functional React component update using Tailwind CSS and Lucide icons.

**Tech Stack:** React (TypeScript), Lucide Icons, Tailwind CSS.

---

### Task 1: Update Imports

**Files:**
- Modify: `frontend-v2/src/components/users/UserTable.tsx`

- [ ] **Step 1: Add Send to lucide-react imports**

```tsx
import { Coins, Gift, Send, Shield, User as UserIcon, Zap } from 'lucide-react';
```

- [ ] **Step 2: Commit**

```bash
git add frontend-v2/src/components/users/UserTable.tsx
git commit -m "chore: add Send icon to UserTable imports"
```

### Task 2: Update Table Header

**Files:**
- Modify: `frontend-v2/src/components/users/UserTable.tsx`

- [ ] **Step 1: Add Phone column to the header**

```tsx
<th className="px-6 py-4 font-medium">User</th>
<th className="px-6 py-4 font-medium">Status</th>
<th className="px-6 py-4 font-medium">Phone</th> {/* Add this */}
<th className="px-6 py-4 font-medium">Balance</th>
```

- [ ] **Step 2: Commit**

```bash
git add frontend-v2/src/components/users/UserTable.tsx
git commit -m "ui: add Phone column to UserTable header"
```

### Task 3: Update Table Body

**Files:**
- Modify: `frontend-v2/src/components/users/UserTable.tsx`

- [ ] **Step 1: Add Phone cell to the row**

```tsx
<td className="px-6 py-4">
  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
    user.account_status === 'active' 
      ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
      : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
  }`}>
    {user.account_status}
  </span>
</td>
<td className="px-6 py-4 font-mono">
  {user.phone_number || '-'}
</td>
<td className="px-6 py-4 font-mono">
  ${user.credit_balance_usd.toFixed(4)}
</td>
```

- [ ] **Step 2: Update colSpan for empty state**

```tsx
{users.length === 0 && (
  <tr>
    <td colSpan={6} className="px-6 py-10 text-center text-muted-foreground">
      No users found.
    </td>
  </tr>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend-v2/src/components/users/UserTable.tsx
git commit -m "ui: add Phone column to UserTable body"
```

### Task 4: Add Message Button

**Files:**
- Modify: `frontend-v2/src/components/users/UserTable.tsx`

- [ ] **Step 1: Add Message button to actions**

```tsx
<div className="inline-flex items-center gap-2">
  <button
    onClick={() => window.location.href = `/messaging?userId=${user.telegram_user_id || user.id}`}
    className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-border bg-background hover:bg-muted transition-colors"
  >
    <Send className="w-3.5 h-3.5" />
    Message
  </button>
  {/* Existing buttons... */}
```

- [ ] **Step 2: Commit**

```bash
git add frontend-v2/src/components/users/UserTable.tsx
git commit -m "feat: add Message button to UserTable actions"
```
