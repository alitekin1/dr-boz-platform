# Design: Default Model Selection

## Objective
Add a configuration option in the admin panel to allow administrators to designate a global "default model". This default model will be used as a fallback for new users or when a specific model isn't chosen.

## 1. Database Schema (`backend/app/models.py`)
-   **Table:** `models`
-   **New Column:** `is_default` (Boolean, default `False`)
-   **Migration:** A migration step will be required to add this column to existing databases (handled in `backend/app/database.py`).

## 2. Backend Logic (`backend/app/admin_routes.py` & `backend/app/schemas.py`)
-   **Schemas:** Include `is_default` in `ModelCreate`, `ModelUpdate`, and `ModelOut`.
-   **Constraint Enforcement:** When a request sets `is_default=True` for a model, the backend will first execute an `UPDATE models SET is_default = False WHERE id != :id` query to ensure mutual exclusivity.
-   **Activity Requirement:** A model must be active (`is_active=True`) to be set as default. The UI or backend will prevent setting an inactive model as default.

## 3. Bot Fallback Logic (`backend/app/bot.py`)
-   When initializing a new chat or resolving a missing model ID, the system will first query for the active default model:
    `select(DBModel).where(DBModel.is_active == True, DBModel.is_default == True)`
-   If no default is found (or if it's inactive), it will fallback to the previous behavior of selecting the first available active model.

## 4. Frontend UI (`frontend-v2/src/components/config/`)
-   **Model Form:** Include a checkbox or toggle for "Set as default model".
-   **Model List:** Display a badge (e.g., "DEFAULT" or a star icon) on the model card that is currently set as default to provide immediate visual feedback.
