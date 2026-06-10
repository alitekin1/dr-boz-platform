# RULES

- after you made changes into the codesbase, you should commit and write what you did in short. 


- after every changes, make sure the app, backend and admin panel is running.



# Running the Application

To run the full stack application, you need to start both the UI and the Backend.

## Backend

The backend runs on **port 7000**.
To start the backend, execute the following commands from the root of the project:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
```

## Frontend UI

The frontend runs on **port 4000**.
To start the frontend, execute the following commands from the root of the project:

```bash
cd frontend-v2
npm install
npm run dev -- --port 4000
```

# TIPS Feature
The "TIPS" feature is an educational tooltip system for users. 
Whenever introducing a new capability (e.g., PDF conversion for math formulas), the bot can send a "TIP".
- **Format:** A temporary message explaining the feature.
- **Buttons:** It must include two inline buttons: "متوجه شدم" (Got it) and "دیگر نشان نده" (Don't show again).
- **Behavior:** 
  - "متوجه شدم" deletes the tip message immediately.
  - "دیگر نشان نده" deletes the tip message AND saves a preference in the database so the user never sees this specific tip again.
  - If the user does nothing, the tip message must be **automatically deleted** after a short delay (e.g., 20-30 seconds).
