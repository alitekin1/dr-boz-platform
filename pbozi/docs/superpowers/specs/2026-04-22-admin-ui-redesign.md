# Spec: JGPTi Admin UI Redesign (Vite + TanStack Query)

**Date**: 2026-04-22
**Status**: Approved
**Topic**: Rebuilding the Admin UI from scratch to ensure stability, real-time observability, and "no-lock" responsiveness.

---

## 1. Executive Summary
The previous Admin UI suffered from infinite re-render loops and a brittle data-fetching strategy that "locked" the UI when backend connections were slow or unstable. This redesign moves to a modern, decentralized architecture using **Vite** and **TanStack Query** to ensure the dashboard remains interactive while data refreshes in the background.

## 2. Architecture & Tech Stack
- **Framework**: Vite + React + TypeScript (SPA).
- **Data Management**: TanStack Query (React Query) for asynchronous state, background polling (30s), and automatic retry/cancellation.
- **Styling**: Tailwind CSS + Shadcn/UI (Component Library).
- **Navigation**: Sidebar-Centric responsive layout.
- **Authentication**: Bearer Token (ADMIN_PASSWORD) stored in `localStorage`.
- **API Strategy**: Native `fetch` wrapper with dynamic `API_URL` discovery based on `window.location.hostname`.

## 3. Navigation Structure (Sidebar)
The UI will be organized into five primary clusters:

### 3.1 Overview & Stats
- Real-time metrics cards: Active Users, Registered Models, Usage (Today), Failed Tools.
- System health status (Backend/Bot/DB).

### 3.2 Configuration (Management)
- **Providers**: List/Edit/Create API providers (OpenAI, etc.).
- **Models**: Management of specific model IDs, pricing, and capabilities.
- **System Prompts**: Editor for core instructions and tool guidance.

### 3.3 Intelligence & Search
- **Tools**: Library of available function call definitions.
- **Bindings**: Scoped tool activation (Global/Project/Chat).
- **Web Search**: Configuration for Exa/Google search integration.
- **Embedding**: RAG engine configuration.

### 3.4 User & Finance
- **User Directory**: List of Telegram users with account status.
- **Wallet & Ledger**: Manual credit adjustments, transaction audit trail.
- **Feedback**: Table of user ratings and chat reactions.

### 3.5 Live Monitoring
- **Usage Stream**: Granular view of `UsageEvent` records.
- **Audit Log**: Chronological view of `AdminAction` records.
- **Ops/Debug**: Viewer for Projects, Chats, and Message history.

## 4. UI/UX Principles
- **System/Toggle Theme**: Support for Light, Dark, and System modes.
- **RTL Support**: Native Farsi support for content and layout (`dir="rtl"`).
- **Optimistic UI**: Background loading indicators without blocking user interactions.
- **Resiliency**: Centralized error toasts for 401/404/500 errors.

## 5. Implementation Phases
1. **Foundation**: Vite + Tailwind + TanStack Query setup. Dynamic API config.
2. **Layout**: Responsive sidebar + Theme Toggle.
3. **Core CRUD**: User, Provider, and Model management.
4. **Complex Features**: Tool Bindings, RAG Config, and Usage Logs.
5. **Verification**: End-to-end testing of data flow and background polling.
