# NFL Hub - Deployment Guide

Complete guide for deploying the NFL Hub application with frontend on Vercel and backend on Render.

## Architecture Overview

- **Frontend**: React app deployed to Vercel
- **Backend**: FastAPI Python app deployed to Render
- **Database**: DuckDB (embedded in backend)
- **Auto-deploy**: GitHub Actions workflows trigger deployments on push to main

## Production URLs

- **Frontend**: https://ruberube.vercel.app
- **Backend**: https://nfl-hub-new-1.onrender.com
- **Backend API**: https://nfl-hub-new-1.onrender.com/api

## Frontend Deployment (Vercel)

### Initial Setup

1. Go to https://vercel.com/dashboard
2. Click "New Project" → Import from GitHub
3. Select repository: `RBarbieri13/NFL-HUB-NEW`
4. Configure project settings:
   - **Framework**: Create React App
   - **Root Directory**: `frontend`
   - **Build Command**: `yarn build`
   - **Output Directory**: `build`
   - **Node Version**: 22.x (set in `frontend/package.json` engines)

### Environment Variables

Required environment variable in Vercel:

| Key | Value | Environments |
|-----|-------|--------------|
| `REACT_APP_BACKEND_URL` | `https://nfl-hub-new-1.onrender.com` | Production, Preview, Development |

To set:
1. Go to Vercel project → Settings → Environment Variables
2. Add the variable above
3. Check all three environment boxes (Production, Preview, Development)
4. Click "Save"

### Build Configuration

The frontend uses:
- **Package Manager**: Yarn (do NOT use npm)
- **Node Version**: 22.x (specified in package.json)
- **Build Tool**: Create React App with @craco/craco

**Important Build Notes:**
- Do NOT add `resolutions` to package.json (causes webpack conflicts)
- ajv v8 packages are in devDependencies to fix schema-utils compatibility
- If build fails with webpack errors, verify Node 22.x is being used

### Auto-Deploy Setup (Optional)

1. In Vercel project → Settings → Deploy Hooks
2. Create hook named "GitHub Auto-Deploy"
3. Copy the hook URL
4. Add to GitHub Secrets as `VERCEL_DEPLOY_HOOK_URL`

## Backend Deployment (Render)

### Initial Setup

1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect GitHub repository: `RBarbieri13/NFL-HUB-NEW`
4. Render auto-detects `render.yaml` configuration:
   - **Name**: nfl-hub-new-backend (or your choice)
   - **Environment**: Python 3
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
5. Click "Create Web Service"
6. Wait 3-5 minutes for initial deployment

### Configuration Details

The backend configuration is defined in `render.yaml`:

```yaml
services:
  - type: web
    name: nfl-hub-new-backend
    env: python
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn server:app --host 0.0.0.0 --port $PORT
    autoDeploy: true
    plan: free
    healthCheckPath: /api
```

**Important Notes:**
- Uses `$PORT` environment variable (Render provides this automatically)
- Health check endpoint is `/api` (not `/` or `/health`)
- Free tier spins down after inactivity (50+ second cold start)
- Auto-deploys on push to main when connected to GitHub

### Auto-Deploy Setup (Optional)

1. In Render service → Settings → Deploy Hook
2. Enable deploy hook and copy URL
3. Add to GitHub Secrets as `RENDER_DEPLOY_HOOK_URL`

## Local Development

### Frontend

1. Create `frontend/.env` file:
   ```
   REACT_APP_BACKEND_URL=http://localhost:10000
   ```
   Or use the production backend URL for testing:
   ```
   REACT_APP_BACKEND_URL=https://nfl-hub-new-1.onrender.com
   ```

2. Install dependencies and start:
   ```bash
   cd frontend
   yarn install
   yarn start
   ```

3. Open http://localhost:3000

### Backend

1. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Start server:
   ```bash
   uvicorn server:app --reload --port 10000
   ```

3. API available at http://localhost:10000/api

## Verification & Testing

### Test Backend API

```bash
# Check API root
curl https://nfl-hub-new-1.onrender.com/api

# Get player data
curl https://nfl-hub-new-1.onrender.com/api/players?limit=5

# Expected response: JSON array of player objects
```

### Test Frontend

1. Open https://ruberube.vercel.app
2. Verify player data loads (should show "X players" in header)
3. Check browser console for errors (AG Grid warnings are harmless)
4. Test navigation between Data Table and Trend Tool tabs

### Common Issues

**Frontend shows "0 players":**
- Check `REACT_APP_BACKEND_URL` is set in Vercel
- Verify backend is running (not cold-started)
- Check browser console for CORS errors

**Backend returns 404:**
- Verify you're hitting `/api` endpoint (not `/`)
- Check Render service is running (not suspended)

**Build fails on Vercel:**
- Verify Node 22.x is configured
- Check no `resolutions` in package.json
- Review build logs for specific webpack errors

## GitHub Actions Auto-Deploy

The repository includes workflows in `.github/workflows/`:

- **auto-deploy.yml**: Triggers deploy hooks on push to main
- **deploy.yml**: Full CI/CD workflow (tests + deploy)

### Required GitHub Secrets

Add these in repository Settings → Secrets and variables → Actions:

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `VERCEL_DEPLOY_HOOK_URL` | Vercel deploy hook | Vercel project → Settings → Deploy Hooks |
| `RENDER_DEPLOY_HOOK_URL` | Render deploy hook | Render service → Settings → Deploy Hook |

### Workflow Behavior

On push to `main`:
1. GitHub Actions triggers
2. Calls Vercel deploy hook (frontend rebuilds)
3. Calls Render deploy hook (backend rebuilds)
4. Both deployments complete in 2-5 minutes

## Known Build Pitfalls & Solutions

### Issue: Vercel build fails with webpack errors

**Symptoms:**
- "Cannot find module 'ajv/dist/compile/codegen'"
- "validateOptions is not a function"

**Solution:**
- Use Node 22.x (set in package.json engines)
- Do NOT add package.json "resolutions" section
- Ensure ajv v8 packages are in devDependencies:
  ```json
  "devDependencies": {
    "ajv": "^8.12.0",
    "ajv-formats": "^2.1.1",
    "ajv-keywords": "^5.1.0"
  }
  ```

### Issue: Render deployment fails

**Symptoms:**
- "No open ports detected"
- Health check fails

**Solution:**
- Verify `startCommand` uses `$PORT` (not hardcoded port)
- Verify `healthCheckPath` is `/api` (not `/`)
- Check `rootDir` is set to `backend`

### Issue: Frontend can't connect to backend

**Symptoms:**
- "0 players" shown
- CORS errors in browser console

**Solution:**
- Set `REACT_APP_BACKEND_URL` in Vercel environment variables
- Verify backend CORS settings allow Vercel domain
- Check backend is running (not cold-started on free tier)

## Project Structure

```
NFL-HUB-NEW/
├── frontend/               # React frontend
│   ├── src/
│   │   ├── App.js         # Main application component
│   │   └── components/    # UI components
│   ├── package.json       # Node dependencies
│   ├── vercel.json        # Vercel configuration
│   └── .env.example       # Environment variable template
├── backend/               # FastAPI backend
│   ├── server.py          # Main API server
│   ├── requirements.txt   # Python dependencies
│   └── data/             # DuckDB database files
├── render.yaml           # Render deployment config
├── .github/workflows/    # GitHub Actions workflows
└── DEPLOYMENT.md         # This file
```

## Additional Resources

- **Vercel Documentation**: https://vercel.com/docs
- **Render Documentation**: https://render.com/docs
- **Create React App**: https://create-react-app.dev/
- **FastAPI**: https://fastapi.tiangolo.com/

## Support & Troubleshooting

If you encounter issues:

1. Check deployment logs:
   - Vercel: Project → Deployments → Click deployment → View logs
   - Render: Service → Logs tab

2. Verify environment variables are set correctly

3. Test API endpoints directly with curl

4. Check browser console for frontend errors

5. Review this guide's "Known Build Pitfalls" section

---

**Last Updated**: November 11, 2025  
**Status**: Production deployment active and working
