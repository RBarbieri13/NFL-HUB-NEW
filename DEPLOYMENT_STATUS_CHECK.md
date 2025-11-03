# 🚀 NFL Hub - Deployment Status Check

## Current Status Overview

### ✅ What's Already Set Up

1. **GitHub Repository**: https://github.com/RBarbieri13/NFL-HUB-NEW
2. **Vercel Deployment**: Already linked (ruberube.vercel.app visible in repo)
3. **Configuration Files Created**:
   - ✅ `frontend/vercel.json` - Vercel deployment config
   - ✅ `render.yaml` - Render backend deployment config
   - ✅ `.github/workflows/auto-deploy.yml` - Auto-deploy workflow (hook-based)
   - ✅ `.github/workflows/deploy.yml` - Full CI/CD workflow (tests + deploy)

### ⚠️ What Needs to Be Done

## Step 1: Verify Vercel Project Setup

**Check if project is properly configured:**

1. Go to: https://vercel.com/dashboard
2. Find your project (likely named "NFL-HUB-NEW" or "ruberube")
3. Check Settings → General:
   - Root Directory: Should be `frontend`
   - Framework: React
   - Build Command: `yarn build`
   - Output Directory: `build`
4. Get your live URL: Should be something like `https://nfl-hub-new.vercel.app` or `https://ruberube.vercel.app`

**Create Deploy Hook:**
1. In Vercel project → Settings → Deploy Hooks
2. Create a new hook named "GitHub Auto-Deploy"
3. Copy the hook URL (looks like: `https://api.vercel.com/v1/integrations/deploy/xxx`)

## Step 2: Set Up Render Backend

1. Go to: https://dashboard.render.com
2. Click "New" → "Web Service"
3. Connect your GitHub repo: `RBarbieri13/NFL-HUB-NEW`
4. Render should auto-detect `render.yaml`:
   - Name: `nfl-hub-new-backend`
   - Root Directory: `backend`
   - Start Command: `uvicorn server:app --host 0.0.0.0 --port 10000`
5. Deploy the service
6. Copy your backend URL: `https://nfl-hub-new-backend.onrender.com`

**Create Deploy Hook:**
1. In Render service → Settings → Deploy Hook
2. Enable the deploy hook and copy the URL

## Step 3: Add GitHub Secrets

**Required Secrets for Auto-Deploy:**

1. Go to: https://github.com/RBarbieri13/NFL-HUB-NEW/settings/secrets/actions
2. Add these secrets:

   - **VERCEL_DEPLOY_HOOK_URL**: Paste the Vercel deploy hook URL
   - **RENDER_DEPLOY_HOOK_URL**: Paste the Render deploy hook URL

## Step 4: Configure Frontend Environment Variable

**Update Vercel Environment Variables:**

1. In Vercel project → Settings → Environment Variables
2. Add:
   - `REACT_APP_BACKEND_URL` = `https://nfl-hub-new-backend.onrender.com` (or your Render URL)
3. Redeploy the frontend

## Step 5: Test Auto-Deploy

**Make a test change:**

1. Edit any file (e.g., change a color in `frontend/src/App.js`)
2. Commit and push:
   ```bash
   git add .
   git commit -m "test: verify auto-deploy"
   git push origin main
   ```
3. Check:
   - GitHub Actions tab should show workflow running
   - Vercel should trigger a new deployment
   - Render should trigger a new deployment
   - Your live URLs should update within 1-3 minutes

## Verification Checklist

- [ ] Vercel project exists and is linked to GitHub repo
- [ ] Vercel deploy hook created and added to GitHub secrets
- [ ] Render backend service created and deployed
- [ ] Render deploy hook created and added to GitHub secrets
- [ ] Frontend environment variable `REACT_APP_BACKEND_URL` set in Vercel
- [ ] Test commit triggers both deployments successfully
- [ ] Live frontend URL shows the latest code
- [ ] Live backend URL responds to API requests

## Expected URLs After Setup

- **Frontend**: `https://nfl-hub-new.vercel.app` (or your Vercel project name)
- **Backend**: `https://nfl-hub-new-backend.onrender.com`

## Troubleshooting

**If auto-deploy doesn't work:**

1. Check GitHub Actions tab for workflow errors
2. Verify secrets are correctly named (case-sensitive)
3. Check Vercel/Render deployment logs
4. Ensure `main` branch is the default branch

**If frontend can't connect to backend:**

1. Verify `REACT_APP_BACKEND_URL` is set in Vercel
2. Check CORS settings in `backend/server.py`
3. Verify Render backend is running and accessible

## Quick Test Command

```bash
# Test backend is accessible
curl https://nfl-hub-new-backend.onrender.com/api/health

# Check frontend loads
curl -I https://nfl-hub-new.vercel.app
```

---

**Last Updated**: After auto-deploy setup completed
**Status**: Configuration files ready, awaiting manual setup steps


