# DeployAI Platform — Setup Guide

## Architecture Overview

```
User Browser
    ↓ HTTP
Nginx (port 80) — Frontend React App
    ↓ /api/* proxy
FastAPI Backend (port 8000)
    ↓
Deployment Engine
    ├── GitPython — Clone repos
    ├── Stack Detector — Auto-detect framework
    ├── AI Dockerfile Generator — Groq/OpenAI/Gemini
    ├── Fallback Template Engine — Rule-based Dockerfiles
    ├── subprocess — docker build + docker run
    └── Dynamic Port Allocator (8100–9000)
        ↓
Docker Runtime — User app containers
```

---

## Prerequisites

```bash
# On your Ubuntu EC2 instance:
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Install Git
sudo apt install git -y
```

---

## Deployment Steps

### 1. Clone / Upload this project
```bash
# Upload via scp or git clone your repo
scp -r deployai/ ubuntu@YOUR_EC2_IP:~/deployai
```

### 2. Configure Environment
```bash
cd ~/deployai
```

No mandatory env vars — AI API key is entered via the UI Settings panel.

### 3. Open required ports in EC2 Security Group

| Port | Purpose |
|------|---------|
| 22   | SSH |
| 80   | Frontend + API |
| 8000 | FastAPI (optional direct access) |
| 8100–9000 | Dynamic user app ports |

### 4. Launch the Platform
```bash
cd ~/deployai
docker compose up -d --build
```

### 5. Access the UI
```
http://YOUR_EC2_PUBLIC_IP
```

---

## How to Use

1. Open the platform in your browser
2. Enter a **Project Name** (e.g., `my-flask-app`)
3. Paste a **Public GitHub Repo URL** (e.g., `https://github.com/user/repo`)
4. *(Optional)* Click **Settings** → add your Groq/OpenAI/Gemini API key for AI Dockerfile generation
5. Click **Analyze & Deploy**
6. Watch real-time logs:
   - Cloning
   - Stack detection
   - AI Dockerfile generation (or fallback)
   - Docker build
   - Container start
7. Get your **Public URL**: `http://YOUR_EC2_IP:PORT`

---

## Supported Stacks (Auto-Detected)

| Indicator File | Detected Framework | Internal Port |
|----------------|-------------------|---------------|
| `package.json` + React/Vite | React/Vite | 5173 |
| `package.json` + Next.js | Next.js | 3000 |
| `package.json` + Express | Express.js | 3000 |
| `package.json` (generic) | Node.js | 3000 |
| `requirements.txt` + Flask | Flask | 5000 |
| `requirements.txt` + FastAPI | FastAPI | 8000 |
| `requirements.txt` + Django | Django | 8000 |
| `requirements.txt` + Streamlit | Streamlit | 8501 |
| `pom.xml` | Java Maven | 8080 |
| `build.gradle` | Spring Boot | 8080 |
| `go.mod` | Go | 8080 |
| `Cargo.toml` | Rust | 8080 |
| `index.html` only | Static HTML | 80 |
| `Dockerfile` present | Custom Docker | 8080 |

---

##  AI Integration

### Groq (Recommended — Free tier available)
1. Get key at: https://console.groq.com
2. Click Settings in the UI
3. Select "Groq", paste key

### OpenAI
1. Get key at: https://platform.openai.com
2. Select "OpenAI (GPT-4o mini)"

### Gemini
1. Get key at: https://aistudio.google.com
2. Select "Google Gemini"

### Fallback (No key required)
If no key is provided or AI fails, the platform automatically uses rule-based Dockerfile templates — deployments always work.

---

## Monitoring

```bash
# View platform logs
docker compose logs -f

# List deployed user containers
docker ps --filter "label=deployai.project"

# Stop a specific user app
docker stop deployai-myapp-XXXXXXXX

# Platform health
curl http://localhost:8000/api/health

# List all deployments via API
curl http://localhost:8000/api/deployments
```

---

## Maintenance

```bash
# Stop the platform
docker compose down

# Clean up all user app containers
docker ps -q --filter "label=deployai.project" | xargs docker stop | xargs docker rm

# Remove all deployai images
docker images --filter "reference=deployai-*" -q | xargs docker rmi

# Full reset
docker compose down && docker system prune -f && docker compose up -d --build
```

---

## Custom Domain (Optional)

For `myapp.deployai.com` style subdomains:

1. Point `*.deployai.com` DNS → EC2 IP
2. Add Traefik or Nginx virtual host routing
3. Update `generate_deployment_url()` in `backend/main.py` to return subdomain

---

## ⚡ API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/deploy` | Start a deployment |
| GET | `/api/deployments` | List all deployments |
| GET | `/api/deployments/{id}` | Get deployment details |
| GET | `/api/deployments/{id}/logs?since=N` | Get logs (paginated) |
| DELETE | `/api/deployments/{id}` | Stop & delete deployment |
| GET | `/api/health` | Platform health check |

### Deploy Request Body
```json
{
  "project_name": "my-app",
  "repo_url": "https://github.com/user/repo",
  "ai_api_key": "gsk_...",
  "ai_provider": "groq"
}
```

