# Here are your Instructions

Updated via Desktop Commander to trigger CI deploy.

## Testing URL (auto-updating) setup

1) Frontend (Vercel)
- Import this GitHub repo into Vercel.
- Framework: React. Root Directory: `frontend`. Build: `yarn build`. Output: `build`.
- Result: a persistent URL like `https://<your-project>.vercel.app` that always serves the latest `main`.

2) Backend (Render)
- Create a Web Service from this repo in Render.
- It will pick up `render.yaml`. Root Directory: `backend`.
- Start command: `uvicorn server:app --host 0.0.0.0 --port 10000`.
- Result: backend URL like `https://nfl-hub-new-backend.onrender.com`.

3) Auto-deploy on push
- In GitHub repo settings → Secrets and variables → Actions, add:
  - `VERCEL_DEPLOY_HOOK_URL` (from Vercel Project → Settings → Deploy Hooks)
  - `RENDER_DEPLOY_HOOK_URL` (from Render Service → Settings → Deploy Hook)
- The workflow at `.github/workflows/deploy.yml` triggers both hooks on every push to `main`.

Notes
- Frontend config: `frontend/vercel.json`.
- Backend infra config: `render.yaml`.
- After wiring, any commit to `main` auto-updates the testing URLs to the current version.
