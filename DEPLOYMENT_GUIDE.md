# 🚀 NFL Hub - Deployment & CI/CD Setup Guide

## Table of Contents
- [Overview](#overview)
- [Local Development Setup](#local-development-setup)
- [GitHub Actions CI/CD](#github-actions-cicd)
- [Deployment Options](#deployment-options)
- [Environment Variables](#environment-variables)

---

## Overview

This project uses **GitHub Actions** for automated testing and deployment. The workflow is configured to:
- ✅ Run automated tests on every push/PR
- ✅ Build and validate the application
- ✅ Deploy automatically to your chosen platform
- ✅ Support multiple deployment strategies (Vercel, SSH, Docker)

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Yarn package manager
- Git with SSH access to GitHub

### Quick Start

1. **Clone the repository** (already done! ✅)
```bash
cd /Users/robert.barbieri/Projects/NFL-HUB-NEW
```

2. **Backend Setup**
```bash
cd backend
source venv/bin/activate  # Virtual environment already created!
# Dependencies already installed!
```

3. **Frontend Setup**
```bash
cd frontend
# Dependencies already installed!
```

4. **Environment Variables**
Both `.env` files are already created:
- `backend/.env` - Backend configuration
- `frontend/.env` - Frontend configuration

5. **Start Development Servers**

Terminal 1 - Backend:
```bash
cd backend
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Terminal 2 - Frontend:
```bash
cd frontend
yarn start
```

6. **Load Initial Data**
```bash
curl -X POST http://localhost:8001/api/load-data
```

7. **Open Browser**
```
http://localhost:3000
```

---

## GitHub Actions CI/CD

### What's Already Configured

The workflow file `.github/workflows/deploy.yml` includes:

1. **test-backend**: Tests Python backend code
2. **test-frontend**: Builds and validates React frontend
3. **deploy-vercel**: Deploys to Vercel (when secrets configured)
4. **deploy-backend-ssh**: Deploys backend via SSH (when secrets configured)
5. **deploy-docker**: Builds and pushes Docker images (optional)

### Current Status

✅ Workflow file created and ready
⏳ Secrets need to be configured for deployment

---

## Deployment Options

### Option 1: Vercel (Recommended for Quick Deploy)

**Best for**: Full-stack apps with serverless backend

1. **Create Vercel Account**
   - Go to https://vercel.com
   - Sign up/login with GitHub

2. **Get Vercel Tokens**
   ```bash
   # Install Vercel CLI
   npm install -g vercel
   
   # Login and get credentials
   vercel login
   vercel link
   ```

3. **Add GitHub Secrets**
   Go to: `https://github.com/RBarbieri13/NFL-HUB-NEW/settings/secrets/actions`
   
   Add these secrets:
   - `VERCEL_TOKEN`: Your Vercel auth token
   - `VERCEL_ORG_ID`: From `.vercel/project.json`
   - `VERCEL_PROJECT_ID`: From `.vercel/project.json`
   - `REACT_APP_BACKEND_URL`: Your production backend URL

4. **Deploy**
   ```bash
   git add .
   git commit -m "feat: Setup GitHub Actions deployment [deploy]"
   git push origin main
   ```

---

### Option 2: SSH Deploy to Your Server

**Best for**: When you have your own server (AWS, DigitalOcean, etc.)

1. **Prepare Your Server**
   ```bash
   # On your server
   sudo apt update
   sudo apt install python3.11 python3-pip nodejs npm
   cd /var/www
   git clone git@github.com:RBarbieri13/NFL-HUB-NEW.git
   ```

2. **Generate SSH Key for GitHub Actions**
   ```bash
   ssh-keygen -t ed25519 -C "github-actions@nfl-hub"
   # Add public key to server's ~/.ssh/authorized_keys
   ```

3. **Add GitHub Secrets**
   - `SSH_HOST`: Your server IP/domain
   - `SSH_USERNAME`: Server username
   - `SSH_KEY`: Private SSH key content

4. **Update workflow** (edit `.github/workflows/deploy.yml`):
   ```yaml
   # Line 114: Update the path
   script: |
     cd /var/www/NFL-HUB-NEW/backend
     ...
   ```

---

### Option 3: Docker Deploy

**Best for**: Containerized deployments (Docker, Kubernetes)

1. **Create Dockerfiles**

**backend/Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
```

**frontend/Dockerfile**:
```dockerfile
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile
COPY . .
RUN yarn build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

2. **Add GitHub Secrets**
   - `DOCKER_USERNAME`: Docker Hub username
   - `DOCKER_PASSWORD`: Docker Hub password/token

3. **Deploy with Docker**
   ```bash
   git commit -m "feat: Docker deployment [docker]"
   git push origin main
   ```

---

## Environment Variables

### Backend (`backend/.env`)
```env
MONGO_URL=mongodb://localhost:27017/nfl_fantasy
API_HOST=0.0.0.0
API_PORT=8001
CORS_ORIGINS=http://localhost:3000
```

### Frontend (`frontend/.env`)
```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

### GitHub Secrets (Production)

Required for deployment:
- `REACT_APP_BACKEND_URL`: Production backend URL
- Plus deployment-specific secrets (Vercel, SSH, or Docker)

---

## Testing the CI/CD Pipeline

### Manual Test
```bash
# Trigger workflow manually
git add .
git commit -m "test: Trigger CI/CD pipeline"
git push origin main
```

### View Workflow Status
1. Go to: https://github.com/RBarbieri13/NFL-HUB-NEW/actions
2. Click on the latest workflow run
3. View logs for each job

### Deployment Triggers

- **Automatic**: Every push to `main` branch
- **Manual**: Click "Run workflow" in GitHub Actions tab
- **Docker**: Add `[docker]` to commit message
- **Skip**: Add `[skip ci]` to commit message

---

## Common Issues & Troubleshooting

### Issue: "No secrets configured"
**Solution**: Deployment jobs will skip if secrets aren't set up. This is normal.

### Issue: "Port already in use"
**Solution**: 
```bash
# Kill process on port 8001
lsof -ti:8001 | xargs kill -9

# Or use different port
uvicorn server:app --port 8002
```

### Issue: "Module not found"
**Solution**:
```bash
# Backend
cd backend && pip install -r requirements.txt

# Frontend
cd frontend && yarn install
```

### Issue: "CORS errors"
**Solution**: Check `.env` files match your URLs

---

## Next Steps

1. ✅ Local development environment is ready
2. ⏳ Configure GitHub secrets for your deployment platform
3. ⏳ Push code to trigger first deployment
4. ⏳ Monitor workflow in GitHub Actions
5. ⏳ Access your deployed app!

---

## Deployment Checklist

- [ ] Choose deployment platform (Vercel/SSH/Docker)
- [ ] Add required GitHub secrets
- [ ] Update environment variables for production
- [ ] Test deployment workflow
- [ ] Configure custom domain (optional)
- [ ] Set up monitoring/logging (optional)
- [ ] Create backup strategy (optional)

---

## Additional Resources

- **GitHub Actions**: https://docs.github.com/actions
- **Vercel Deployment**: https://vercel.com/docs
- **Docker Guide**: https://docs.docker.com/get-started/
- **FastAPI Deployment**: https://fastapi.tiangolo.com/deployment/

---

**🎉 Your NFL Hub is ready for deployment!**

Need help? Check the logs in GitHub Actions or review this guide.
