import os
import uuid
import json
import socket
import shutil
import asyncio
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

import git
import docker
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="DeployAI Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE = Path("/tmp/deployai_workspace")
WORKSPACE.mkdir(exist_ok=True)

deployments = {}

class DeployRequest(BaseModel):
    project_name: str
    repo_url: str
    ai_api_key: Optional[str] = None
    ai_provider: Optional[str] = "groq"  # groq, openai, gemini

def log(deployment_id: str, message: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"timestamp": ts, "message": message, "level": level}
    if deployment_id in deployments:
        deployments[deployment_id]["logs"].append(entry)
    print(f"[{deployment_id[:8]}] [{level.upper()}] {message}")

def find_free_port(start=8100, end=9000):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports available")

def detect_stack(repo_path: Path) -> dict:
    files = [f.name for f in repo_path.rglob("*") if f.is_file()]
    root_files = [f.name for f in repo_path.iterdir() if f.is_file()]

    stack = {"framework": "unknown", "language": "unknown", "internal_port": 3000, "build_cmd": None, "start_cmd": None}

    if "Dockerfile" in root_files:
        stack.update({"framework": "docker", "language": "docker", "internal_port": 8080})
    elif "package.json" in root_files:
        pkg = json.loads((repo_path / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "next" in deps:
            stack.update({"framework": "nextjs", "language": "nodejs", "internal_port": 3000})
        elif "react" in deps or "vite" in deps:
            stack.update({"framework": "react", "language": "nodejs", "internal_port": 5173})
        elif "express" in deps:
            stack.update({"framework": "express", "language": "nodejs", "internal_port": 3000})
        elif "fastify" in deps:
            stack.update({"framework": "fastify", "language": "nodejs", "internal_port": 3000})
        else:
            stack.update({"framework": "nodejs", "language": "nodejs", "internal_port": 3000})
    elif "requirements.txt" in root_files or "pyproject.toml" in root_files:
        content = ""
        if (repo_path / "requirements.txt").exists():
            content = (repo_path / "requirements.txt").read_text().lower()
        if "django" in content:
            stack.update({"framework": "django", "language": "python", "internal_port": 8000})
        elif "fastapi" in content or "uvicorn" in content:
            stack.update({"framework": "fastapi", "language": "python", "internal_port": 8000})
        elif "flask" in content:
            stack.update({"framework": "flask", "language": "python", "internal_port": 5000})
        elif "streamlit" in content:
            stack.update({"framework": "streamlit", "language": "python", "internal_port": 8501})
        else:
            stack.update({"framework": "python", "language": "python", "internal_port": 8000})
    elif "pom.xml" in root_files:
        stack.update({"framework": "maven", "language": "java", "internal_port": 8080})
    elif "build.gradle" in root_files:
        stack.update({"framework": "gradle", "language": "java", "internal_port": 8080})
    elif "go.mod" in root_files:
        stack.update({"framework": "go", "language": "go", "internal_port": 8080})
    elif "Cargo.toml" in root_files:
        stack.update({"framework": "rust", "language": "rust", "internal_port": 8080})
    elif "index.html" in root_files:
        stack.update({"framework": "static", "language": "html", "internal_port": 80})

    return stack

def generate_dockerfile_ai(repo_path: Path, stack: dict, api_key: str, provider: str) -> Optional[str]:
    try:
        file_list = []
        for f in repo_path.rglob("*"):
            if f.is_file() and not any(p in str(f) for p in [".git", "node_modules", "__pycache__", ".env"]):
                rel = str(f.relative_to(repo_path))
                file_list.append(rel)

        key_files = {}
        for fname in ["package.json", "requirements.txt", "pom.xml", "build.gradle", "go.mod", "Cargo.toml"]:
            fpath = repo_path / fname
            if fpath.exists():
                try:
                    key_files[fname] = fpath.read_text()[:2000]
                except:
                    pass

        prompt = f"""You are a Docker expert. Generate a production-ready, optimized Dockerfile for this repository.

Stack detected: {json.dumps(stack, indent=2)}

Repository files:
{chr(10).join(file_list[:80])}

Key configuration files:
{json.dumps(key_files, indent=2)}

Requirements:
1. Use official, minimal base images (alpine/slim preferred)
2. Multi-stage builds where beneficial
3. Proper layer caching (dependencies before source code)
4. Non-root user for security
5. Health check instruction
6. The app MUST listen on port {stack['internal_port']}
7. Handle all dependencies correctly
8. Set appropriate environment variables

Return ONLY the Dockerfile content, no explanations, no markdown fences."""

        if provider == "groq":
            import urllib.request
            data = json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.1
            }).encode()
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=data,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"].strip()

        elif provider == "openai":
            import urllib.request
            data = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.1
            }).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"].strip()

        elif provider == "gemini":
            import urllib.request
            data = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 2000, "temperature": 0.1}
            }).encode()
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                return result["candidates"][0]["content"]["parts"][0]["text"].strip()

    except Exception as e:
        return None

def generate_dockerfile_fallback(repo_path: Path, stack: dict) -> str:
    fw = stack["framework"]
    lang = stack["language"]
    port = stack["internal_port"]

    if fw == "docker":
        if (repo_path / "Dockerfile").exists():
            return (repo_path / "Dockerfile").read_text()

    if fw in ("react", "nextjs", "vite"):
        return f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port} || exit 1
CMD ["npm", "start"]
"""

    if fw in ("express", "fastify", "nodejs"):
        return f"""FROM node:20-alpine
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY package*.json ./
RUN npm ci --only=production --prefer-offline
COPY . .
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port} || exit 1
CMD ["node", "index.js"]
"""

    if fw == "nextjs":
        return f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER appuser
EXPOSE {port}
ENV PORT={port}
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port} || exit 1
CMD ["node", "server.js"]
"""

    if fw in ("flask",):
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN addgroup --system appgroup && adduser --system --group appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}')"
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
CMD ["flask", "run", "--host=0.0.0.0", "--port={port}"]
"""

    if fw in ("fastapi", "python"):
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN addgroup --system appgroup && adduser --system --group appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
"""

    if fw == "django":
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN addgroup --system appgroup && adduser --system --group appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN python manage.py collectstatic --noinput 2>/dev/null || true
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:{port}", "--workers", "2", "wsgi:application"]
"""

    if fw == "streamlit":
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN addgroup --system appgroup && adduser --system --group appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}')" || exit 1
CMD ["streamlit", "run", "app.py", "--server.port={port}", "--server.address=0.0.0.0"]
"""

    if fw in ("maven", "gradle", "java"):
        build_tool = "mvn package -DskipTests" if fw == "maven" else "gradle build"
        builder = "maven:3.9-eclipse-temurin-17" if fw == "maven" else "gradle:8-jdk17"
        return f"""FROM {builder} AS builder
WORKDIR /app
COPY . .
RUN {build_tool}

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/target/*.jar app.jar 2>/dev/null || COPY --from=builder /app/build/libs/*.jar app.jar
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port}/actuator/health || exit 1
CMD ["java", "-jar", "app.jar"]
"""

    if fw == "go":
        return f"""FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

FROM alpine:latest
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/main .
RUN chown appuser:appgroup main
USER appuser
EXPOSE {port}
HEALTHCHECK --interval=30s CMD wget -qO- http://localhost:{port}/health || exit 1
CMD ["./main"]
"""

    if fw == "static":
        return f"""FROM nginx:alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY . /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf 2>/dev/null || true
EXPOSE 80
HEALTHCHECK --interval=30s CMD wget -qO- http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
"""

    # Generic fallback
    return f"""FROM ubuntu:22.04
WORKDIR /app
COPY . .
EXPOSE {port}
CMD ["sh", "-c", "echo 'App running' && sleep infinity"]
"""

def run_deployment(deployment_id: str, project_name: str, repo_url: str, ai_api_key: str, ai_provider: str):
    d = deployments[deployment_id]
    d["status"] = "cloning"
    repo_path = WORKSPACE / deployment_id

    try:
        # Phase 1: Clone
        log(deployment_id, f"🔍 Cloning repository: {repo_url}")
        try:
            git.Repo.clone_from(repo_url, str(repo_path), depth=1)
            log(deployment_id, "✅ Repository cloned successfully")
        except git.exc.GitCommandError as e:
            log(deployment_id, f"❌ Failed to clone repository: {str(e)}", "error")
            d["status"] = "failed"
            d["error"] = "Repository clone failed. Check if the URL is valid and the repo is public."
            return

        # Phase 2: Stack Detection
        d["status"] = "analyzing"
        log(deployment_id, "🔎 Analyzing repository structure...")
        stack = detect_stack(repo_path)
        log(deployment_id, f"✅ Stack detected: {stack['framework'].upper()} ({stack['language']}) — internal port {stack['internal_port']}")
        d["stack"] = stack

        # Phase 3: Dockerfile Generation
        d["status"] = "generating"
        dockerfile_content = None

        if ai_api_key:
            log(deployment_id, f"🤖 Generating AI-optimized Dockerfile via {ai_provider.upper()}...")
            dockerfile_content = generate_dockerfile_ai(repo_path, stack, ai_api_key, ai_provider)
            if dockerfile_content:
                log(deployment_id, "✅ AI-generated Dockerfile ready")
            else:
                log(deployment_id, "⚠️ AI generation failed — switching to fallback templates", "warning")

        if not dockerfile_content:
            log(deployment_id, "📋 Using rule-based Dockerfile template...")
            dockerfile_content = generate_dockerfile_fallback(repo_path, stack)
            log(deployment_id, "✅ Fallback Dockerfile generated")

        dockerfile_path = repo_path / "Dockerfile"
        if stack["framework"] != "docker":
            dockerfile_path.write_text(dockerfile_content)

        d["dockerfile"] = dockerfile_content

        # Phase 4: Docker Build
        d["status"] = "building"
        image_tag = f"deployai-{project_name.lower().replace(' ', '-')}-{deployment_id[:8]}"
        log(deployment_id, f"🔨 Building Docker image: {image_tag}")

        build_proc = subprocess.Popen(
            ["docker", "build", "-t", image_tag, "."],
            cwd=str(repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in build_proc.stdout:
            line = line.strip()
            if line:
                log(deployment_id, f"  {line}")

        build_proc.wait()
        if build_proc.returncode != 0:
            log(deployment_id, "❌ Docker build failed", "error")
            d["status"] = "failed"
            d["error"] = "Docker image build failed. Check logs for details."
            return

        log(deployment_id, "✅ Docker image built successfully")
        d["image_tag"] = image_tag

        # Phase 5: Port Allocation & Run
        d["status"] = "deploying"
        external_port = find_free_port()
        internal_port = stack["internal_port"]
        subdomain = f"{project_name.lower().replace(' ', '-').replace('_', '-')}"
        container_name = f"deployai-{subdomain}-{deployment_id[:8]}"

        log(deployment_id, f"🚀 Allocating port {external_port} → container:{internal_port}")
        log(deployment_id, f"🐳 Starting container: {container_name}")

        run_proc = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", container_name,
                "-p", f"{external_port}:{internal_port}",
                "--restart", "unless-stopped",
                "--label", f"deployai.project={project_name}",
                "--label", f"deployai.id={deployment_id}",
                image_tag
            ],
            capture_output=True, text=True
        )

        if run_proc.returncode != 0:
            log(deployment_id, f"❌ Container start failed: {run_proc.stderr}", "error")
            d["status"] = "failed"
            d["error"] = f"Container failed to start: {run_proc.stderr}"
            return

        container_id = run_proc.stdout.strip()[:12]
        log(deployment_id, f"✅ Container started: {container_id}")
        log(deployment_id, f"🌐 Generating public URL...")

        # Detect server IP
        try:
            hostname = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.strip().split()[0]
        except:
            hostname = "localhost"

        public_url = f"http://{hostname}:{external_port}"
        log(deployment_id, f"✅ Deployment complete!")
        log(deployment_id, f"🔗 Public URL: {public_url}")

        d["status"] = "running"
        d["public_url"] = public_url
        d["container_name"] = container_name
        d["container_id"] = container_id
        d["external_port"] = external_port
        d["internal_port"] = internal_port
        d["subdomain"] = subdomain

    except Exception as e:
        log(deployment_id, f"❌ Unexpected error: {str(e)}", "error")
        d["status"] = "failed"
        d["error"] = str(e)
    finally:
        # Cleanup repo directory (keep image)
        if repo_path.exists():
            try:
                shutil.rmtree(str(repo_path))
            except:
                pass


@app.get("/")
def root():
    return {"service": "DeployAI Platform", "version": "1.0.0", "status": "running"}

@app.post("/api/deploy")
async def deploy(req: DeployRequest, background_tasks: BackgroundTasks):
    deployment_id = str(uuid.uuid4())
    deployments[deployment_id] = {
        "id": deployment_id,
        "project_name": req.project_name,
        "repo_url": req.repo_url,
        "status": "queued",
        "logs": [],
        "public_url": None,
        "stack": None,
        "dockerfile": None,
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    background_tasks.add_task(
        run_deployment,
        deployment_id,
        req.project_name,
        req.repo_url,
        req.ai_api_key or "",
        req.ai_provider or "groq"
    )
    return {"deployment_id": deployment_id, "status": "queued"}

@app.get("/api/deployments/{deployment_id}")
def get_deployment(deployment_id: str):
    if deployment_id not in deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployments[deployment_id]

@app.get("/api/deployments/{deployment_id}/logs")
def get_logs(deployment_id: str, since: int = 0):
    if deployment_id not in deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    d = deployments[deployment_id]
    return {
        "logs": d["logs"][since:],
        "total": len(d["logs"]),
        "status": d["status"]
    }

@app.get("/api/deployments")
def list_deployments():
    return [
        {
            "id": d["id"],
            "project_name": d["project_name"],
            "status": d["status"],
            "public_url": d["public_url"],
            "created_at": d["created_at"]
        }
        for d in deployments.values()
    ]

@app.delete("/api/deployments/{deployment_id}")
def delete_deployment(deployment_id: str):
    if deployment_id not in deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")
    d = deployments[deployment_id]
    container = d.get("container_name")
    if container:
        subprocess.run(["docker", "stop", container], capture_output=True)
        subprocess.run(["docker", "rm", container], capture_output=True)
    image = d.get("image_tag")
    if image:
        subprocess.run(["docker", "rmi", image], capture_output=True)
    del deployments[deployment_id]
    return {"status": "deleted"}

@app.get("/api/health")
def health():
    docker_ok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    return {
        "status": "healthy",
        "docker": "available" if docker_ok else "unavailable",
        "active_deployments": len([d for d in deployments.values() if d["status"] == "running"])
    }
