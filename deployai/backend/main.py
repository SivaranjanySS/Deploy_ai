import os
import uuid
import json
import socket
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import git
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
    ai_provider: Optional[str] = "groq"

# ── Logging ──────────────────────────────────────────────────────────────────

def log(deployment_id: str, message: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"timestamp": ts, "message": message, "level": level}
    if deployment_id in deployments:
        deployments[deployment_id]["logs"].append(entry)
    print(f"[{deployment_id[:8]}] [{level.upper()}] {message}", flush=True)

# ── Port allocation ───────────────────────────────────────────────────────────

def get_docker_used_ports() -> set:
    """Return all host ports currently bound by any Docker container (running OR created/stopped)."""
    used = set()
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Ports}}"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            # Lines look like: 0.0.0.0:8100->3000/tcp, 0.0.0.0:80->80/tcp
            for segment in line.split(","):
                segment = segment.strip()
                if "->" in segment:
                    host_part = segment.split("->")[0]          # e.g. 0.0.0.0:8100
                    port_str = host_part.split(":")[-1]         # e.g. 8100
                    if port_str.isdigit():
                        used.add(int(port_str))
    except Exception:
        pass
    return used


def find_free_port(start=8100, end=9000) -> int:
    """Find a port that is free both on the host AND not allocated by any Docker container."""
    docker_ports = get_docker_used_ports()

    for port in range(start, end):
        # Skip ports Docker already knows about (avoids race with 'Created' containers)
        if port in docker_ports:
            continue
        # Also do a real socket bind check for non-Docker processes
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports available in range 8100-9000")

# ── Stack detection ───────────────────────────────────────────────────────────

def detect_stack(repo_path: Path) -> dict:
    root_files = [f.name for f in repo_path.iterdir() if f.is_file()]

    stack = {
        "framework": "unknown",
        "language": "unknown",
        "internal_port": 8080,
        "main_file": None,
    }

    # Existing Dockerfile takes priority
    if "Dockerfile" in root_files:
        stack.update({"framework": "docker", "language": "docker", "internal_port": 8080})
        return stack

    # Node / JS
    if "package.json" in root_files:
        try:
            pkg = json.loads((repo_path / "package.json").read_text(errors="ignore"))
        except Exception:
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        scripts = pkg.get("scripts", {})

        if "next" in deps:
            stack.update({"framework": "nextjs", "language": "nodejs", "internal_port": 3000})
        elif "vite" in deps or "react" in deps:
            stack.update({"framework": "react_vite", "language": "nodejs", "internal_port": 4173})
        elif "express" in deps:
            # detect main entry
            main = pkg.get("main", "index.js")
            stack.update({"framework": "express", "language": "nodejs", "internal_port": 3000, "main_file": main})
        elif "fastify" in deps:
            stack.update({"framework": "fastify", "language": "nodejs", "internal_port": 3000})
        elif "nuxt" in deps:
            stack.update({"framework": "nuxt", "language": "nodejs", "internal_port": 3000})
        else:
            main = pkg.get("main", "index.js")
            stack.update({"framework": "nodejs", "language": "nodejs", "internal_port": 3000, "main_file": main})
        return stack

    # Python
    if "requirements.txt" in root_files or "pyproject.toml" in root_files:
        content = ""
        if (repo_path / "requirements.txt").exists():
            content = (repo_path / "requirements.txt").read_text(errors="ignore").lower()

        # detect main app file
        main_file = "app.py"
        for candidate in ["app.py", "main.py", "application.py", "server.py", "run.py"]:
            if (repo_path / candidate).exists():
                main_file = candidate
                break

        if "django" in content:
            # find manage.py location
            stack.update({"framework": "django", "language": "python", "internal_port": 8000, "main_file": main_file})
        elif "fastapi" in content or "uvicorn" in content:
            stack.update({"framework": "fastapi", "language": "python", "internal_port": 8000, "main_file": main_file})
        elif "flask" in content:
            stack.update({"framework": "flask", "language": "python", "internal_port": 5000, "main_file": main_file})
        elif "streamlit" in content:
            stack.update({"framework": "streamlit", "language": "python", "internal_port": 8501, "main_file": main_file})
        elif "gradio" in content:
            stack.update({"framework": "gradio", "language": "python", "internal_port": 7860, "main_file": main_file})
        else:
            stack.update({"framework": "python", "language": "python", "internal_port": 8000, "main_file": main_file})
        return stack

    # Java
    if "pom.xml" in root_files:
        stack.update({"framework": "maven", "language": "java", "internal_port": 8080})
        return stack
    if "build.gradle" in root_files or "build.gradle.kts" in root_files:
        stack.update({"framework": "gradle", "language": "java", "internal_port": 8080})
        return stack

    # Go
    if "go.mod" in root_files:
        stack.update({"framework": "go", "language": "go", "internal_port": 8080})
        return stack

    # Rust
    if "Cargo.toml" in root_files:
        stack.update({"framework": "rust", "language": "rust", "internal_port": 8080})
        return stack

    # Static HTML
    if "index.html" in root_files:
        stack.update({"framework": "static", "language": "html", "internal_port": 80})
        return stack

    return stack

# ── AI Dockerfile generation ──────────────────────────────────────────────────

import urllib.request
import urllib.error

def _strip_fences(text: str) -> str:
    """Remove markdown code fences that some models add despite instructions."""
    lines = text.strip().split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()

def _call_api(url: str, payload: dict, headers: dict, deployment_id: str):
    """POST to an AI API. Returns raw response string or None. Logs real HTTP errors."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = "(could not read error body)"
        msg = f"AI HTTP {e.code} error: {body[:400]}"
        print(f"[{deployment_id[:8]}] {msg}", flush=True)
        log(deployment_id, f"\u26a0\ufe0f  {msg}", "warning")
        return None
    except urllib.error.URLError as e:
        msg = f"AI network error: {e.reason}"
        print(f"[{deployment_id[:8]}] {msg}", flush=True)
        log(deployment_id, f"\u26a0\ufe0f  {msg}", "warning")
        return None
    except Exception as e:
        msg = f"AI unexpected error: {e}"
        print(f"[{deployment_id[:8]}] {msg}", flush=True)
        log(deployment_id, f"\u26a0\ufe0f  {msg}", "warning")
        return None

def generate_dockerfile_ai(repo_path: Path, stack: dict, api_key: str,
                           provider: str, deployment_id: str = "") -> Optional[str]:
    # Build file context
    file_list = []
    for f in repo_path.rglob("*"):
        if f.is_file() and not any(p in str(f) for p in [".git", "node_modules", "__pycache__", ".env"]):
            file_list.append(str(f.relative_to(repo_path)))

    key_files = {}
    for fname in ["package.json", "requirements.txt", "pom.xml", "build.gradle",
                  "go.mod", "Cargo.toml", "pyproject.toml"]:
        fpath = repo_path / fname
        if fpath.exists():
            try:
                key_files[fname] = fpath.read_text(errors="ignore")[:2000]
            except Exception:
                pass

    prompt = f"""You are a Docker expert. Generate a production-ready Dockerfile for this repository.

Stack detected: {json.dumps(stack)}

Repository files:
{chr(10).join(file_list[:60])}

Key config files:
{json.dumps(key_files, indent=2)}

Rules:
1. Use slim/alpine base images
2. The app MUST listen on port {stack["internal_port"]}
3. Copy dependency files BEFORE source code (layer caching)
4. Handle missing optional files gracefully (use || true)
5. No USER instruction
6. Output ONLY the raw Dockerfile — no markdown fences, no explanation, no preamble"""

    raw = None

    if provider == "groq":
        log(deployment_id, "   \u2192 Calling Groq (llama-3.3-70b-versatile)...")
        raw = _call_api(
            url="https://api.groq.com/openai/v1/chat/completions",
            payload={"model": "llama-3.3-70b-versatile",
                     "messages": [{"role": "user", "content": prompt}],
                     "max_tokens": 1500, "temperature": 0.1},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            deployment_id=deployment_id,
        )
        if raw:
            return _strip_fences(json.loads(raw)["choices"][0]["message"]["content"])

    elif provider == "openai":
        log(deployment_id, "   \u2192 Calling OpenAI (gpt-4o-mini)...")
        raw = _call_api(
            url="https://api.openai.com/v1/chat/completions",
            payload={"model": "gpt-4o-mini",
                     "messages": [{"role": "user", "content": prompt}],
                     "max_tokens": 1500, "temperature": 0.1},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            deployment_id=deployment_id,
        )
        if raw:
            return _strip_fences(json.loads(raw)["choices"][0]["message"]["content"])

    elif provider == "gemini":
        log(deployment_id, "   \u2192 Calling Gemini (gemini-1.5-flash)...")
        raw = _call_api(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            payload={"contents": [{"parts": [{"text": prompt}]}],
                     "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.1}},
            headers={"Content-Type": "application/json"},
            deployment_id=deployment_id,
        )
        if raw:
            return _strip_fences(json.loads(raw)["candidates"][0]["content"]["parts"][0]["text"])

    elif provider == "openrouter":
        log(deployment_id, "   \u2192 Calling OpenRouter (openai/gpt-oss-20b:free)...")
        raw = _call_api(
            url="https://openrouter.ai/api/v1/chat/completions",
            payload={"model": "google/gemma-4-31b-it:free",
                     "messages": [{"role": "user", "content": prompt}],
                     "max_tokens": 1500, "temperature": 0.1},
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "http://localhost",
                     "X-Title": "DeployAI"},
            deployment_id=deployment_id,
        )
        if raw:
            result = json.loads(raw)
            print(f"OPENROUTER RAW RESPONSE: {result}", flush=True)
            if "error" in result:
                err_msg = result["error"].get("message", str(result["error"]))
                log(deployment_id, f"\u26a0\ufe0f  OpenRouter error: {err_msg}", "warning")
                return None
            text = _strip_fences(result["choices"][0]["message"]["content"])
            if text.startswith("```"):
                    text = "\n".join(text.split("\n")[1:])

            if text.endswith("```"):
                    text = "\n".join(text.split("\n")[:-1])

            # Fix invalid Docker image tags generated by AI
            text = text.replace("node:20-slim-alpine", "node:20-alpine")

            return text
    else:
        log(deployment_id, f"\u26a0\ufe0f  Unknown AI provider: {provider}", "warning")

    return None

# ── Fallback Dockerfile templates ────────────────────────────────────────────

def generate_dockerfile_fallback(repo_path: Path, stack: dict) -> str:
    fw  = stack["framework"]
    port = stack["internal_port"]
    main_file = stack.get("main_file") or "app.py"

    # ---------- Use repo's own Dockerfile ----------
    if fw == "docker":
        existing = repo_path / "Dockerfile"
        if existing.exists():
            return existing.read_text()

    # ---------- React / Vite (SPA — serve with nginx) ----------
    if fw == "react_vite":
        # Check whether 'npm run build' output dir is dist or build
        build_dir = "dist"
        try:
            pkg = json.loads((repo_path / "package.json").read_text())
            if "build" in pkg.get("scripts", {}).get("build", ""):
                pass  # vite default is dist
        except Exception:
            pass
        return f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/{build_dir} /usr/share/nginx/html
COPY --from=builder /app/public /usr/share/nginx/html 2>/dev/null || true
RUN echo 'server {{' > /etc/nginx/conf.d/default.conf && \\
    echo '  listen {port};' >> /etc/nginx/conf.d/default.conf && \\
    echo '  root /usr/share/nginx/html;' >> /etc/nginx/conf.d/default.conf && \\
    echo '  index index.html;' >> /etc/nginx/conf.d/default.conf && \\
    echo '  location / {{ try_files $uri $uri/ /index.html; }}' >> /etc/nginx/conf.d/default.conf && \\
    echo '}}' >> /etc/nginx/conf.d/default.conf
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port}/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
"""

    # ---------- Next.js ----------
    if fw == "nextjs":
        return f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build || true

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app ./
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT={port}
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=10s CMD wget -qO- http://localhost:{port}/ || exit 1
CMD ["npm", "start"]
"""

    # ---------- Express / Fastify / generic Node ----------
    if fw in ("express", "fastify", "nodejs", "nuxt"):
        entry = main_file if main_file else "index.js"
        # Try to find the real entry point
        for candidate in ["index.js", "server.js", "app.js", "src/index.js"]:
            if (repo_path / candidate).exists():
                entry = candidate
                break
        return f"""FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
EXPOSE {port}
ENV PORT={port}
ENV NODE_ENV=production
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port}/ || exit 1
CMD ["node", "{entry}"]
"""

    # ---------- Flask ----------
    if fw == "flask":
        # detect app variable name
        app_module = main_file.replace(".py", "")
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
EXPOSE {port}
ENV FLASK_APP={main_file}
ENV FLASK_ENV=production
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:{port}", "--workers", "2", "--timeout", "120", "{app_module}:app"]
"""

    # ---------- FastAPI ----------
    if fw == "fastapi":
        app_module = main_file.replace(".py", "")
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1
CMD ["uvicorn", "{app_module}:app", "--host", "0.0.0.0", "--port", "{port}"]
"""

    # ---------- Django ----------
    if fw == "django":
        # find wsgi/asgi module
        wsgi_module = "wsgi"
        for item in repo_path.rglob("wsgi.py"):
            rel = item.relative_to(repo_path)
            parts = rel.parts
            if len(parts) == 2:
                wsgi_module = f"{parts[0]}.wsgi"
                break
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN python manage.py collectstatic --noinput 2>/dev/null || true
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:{port}", "--workers", "2", "--timeout", "120", "{wsgi_module}:application"]
"""

    # ---------- Streamlit ----------
    if fw == "streamlit":
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1
CMD ["streamlit", "run", "{main_file}", "--server.port={port}", "--server.address=0.0.0.0", "--server.headless=true"]
"""

    # ---------- Gradio ----------
    if fw == "gradio":
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port}
ENV GRADIO_SERVER_PORT={port}
ENV GRADIO_SERVER_NAME=0.0.0.0
HEALTHCHECK --interval=30s --timeout=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/')" || exit 1
CMD ["python", "{main_file}"]
"""

    # ---------- Java Maven ----------
    if fw == "maven":
        return f"""FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -B 2>/dev/null || true
COPY src ./src
RUN mvn package -DskipTests -B

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=10s CMD wget -qO- http://localhost:{port}/actuator/health || exit 1
CMD ["java", "-jar", "app.jar", "--server.port={port}"]
"""

    # ---------- Java Gradle ----------
    if fw == "gradle":
        return f"""FROM gradle:8-jdk17 AS builder
WORKDIR /app
COPY build.gradle* settings.gradle* gradlew* ./
COPY gradle ./gradle 2>/dev/null || true
RUN gradle dependencies --no-daemon 2>/dev/null || true
COPY . .
RUN gradle build -x test --no-daemon

FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=10s CMD wget -qO- http://localhost:{port}/actuator/health || exit 1
CMD ["java", "-jar", "app.jar", "--server.port={port}"]
"""

    # ---------- Go ----------
    if fw == "go":
        return f"""FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o app .

FROM alpine:latest
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /app/app .
EXPOSE {port}
ENV PORT={port}
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:{port}/ || exit 1
CMD ["./app"]
"""

    # ---------- Rust ----------
    if fw == "rust":
        return f"""FROM rust:1.75-alpine AS builder
RUN apk add --no-cache musl-dev
WORKDIR /app
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo 'fn main(){{}}' > src/main.rs && cargo build --release 2>/dev/null; rm -f src/main.rs
COPY . .
RUN cargo build --release

FROM alpine:latest
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /app/target/release/app .
EXPOSE {port}
ENV PORT={port}
CMD ["./app"]
"""

    # ---------- Static HTML ----------
    if fw == "static":
        return f"""FROM nginx:alpine
COPY . /usr/share/nginx/html
RUN echo 'server {{ listen {port}; root /usr/share/nginx/html; index index.html; location / {{ try_files $uri $uri/ /index.html; }} }}' > /etc/nginx/conf.d/default.conf
EXPOSE {port}
HEALTHCHECK --interval=30s CMD wget -qO- http://localhost:{port}/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
"""

    # ---------- Generic Python ----------
    if stack["language"] == "python":
        return f"""FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt* pyproject.toml* ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || pip install --no-cache-dir -e . 2>/dev/null || true
COPY . .
EXPOSE {port}
CMD ["python", "{main_file}"]
"""

    # ---------- Last-resort generic ----------
    return f"""FROM ubuntu:22.04
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY . .
EXPOSE {port}
CMD ["sh", "-c", "echo 'DeployAI: no specific template matched. App is running.' && sleep infinity"]
"""

# ── .dockerignore writer ──────────────────────────────────────────────────────

def write_dockerignore(repo_path: Path):
    """Write a .dockerignore to keep build context lean and avoid conflicts."""
    ignore_content = """.git
.gitignore
*.md
*.log
.env
.env.*
node_modules
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
dist
build
.next
.nuxt
target
*.test.js
*.spec.js
tests/
test/
docs/
.github/
.vscode/
.idea/
"""
    (repo_path / ".dockerignore").write_text(ignore_content)

# ── Main deployment runner ────────────────────────────────────────────────────

def run_deployment(deployment_id: str, project_name: str, repo_url: str, ai_api_key: str, ai_provider: str):
    d = deployments[deployment_id]
    repo_path = WORKSPACE / deployment_id

    try:
        # ── Phase 1: Clone ──────────────────────────────────────────────────
        d["status"] = "cloning"
        log(deployment_id, f"🔍 Cloning repository: {repo_url}")
        try:
            git.Repo.clone_from(repo_url, str(repo_path), depth=1)
            log(deployment_id, "✅ Repository cloned successfully")
        except Exception as e:
            log(deployment_id, f"❌ Clone failed: {str(e)}", "error")
            d["status"] = "failed"
            d["error"] = f"Repository clone failed — make sure the URL is correct and the repo is public.\nDetail: {e}"
            return

        # ── Phase 2: Stack Detection ────────────────────────────────────────
        d["status"] = "analyzing"
        log(deployment_id, "🔎 Analyzing repository structure...")
        stack = detect_stack(repo_path)
        log(deployment_id, f"✅ Stack detected: {stack['framework'].upper()} ({stack['language']}) — internal port {stack['internal_port']}")
        if stack.get("main_file"):
            log(deployment_id, f"   Main entry: {stack['main_file']}")
        d["stack"] = stack

        # ── Phase 3: Dockerfile Generation ─────────────────────────────────
        d["status"] = "generating"
        dockerfile_content = None

        if ai_api_key and ai_api_key.strip():
            log(deployment_id, f"🤖 Generating AI Dockerfile via {ai_provider.upper()}...")
            dockerfile_content = generate_dockerfile_ai(repo_path, stack, ai_api_key.strip(), ai_provider, deployment_id)
            if dockerfile_content:
                log(deployment_id, "✅ AI-generated Dockerfile ready")
            else:
                log(deployment_id, "⚠️  AI generation failed — using fallback template", "warning")

        if not dockerfile_content:
            log(deployment_id, f"📋 Building Dockerfile from {stack['framework']} template...")
            dockerfile_content = generate_dockerfile_fallback(repo_path, stack)
            log(deployment_id, "✅ Dockerfile template ready")

        # Always write Dockerfile (overwrite if already exists — our template is safer)
        dockerfile_path = repo_path / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)
        d["dockerfile"] = dockerfile_content

        # Write lean .dockerignore
        write_dockerignore(repo_path)

        # ── Phase 4: Docker Build ───────────────────────────────────────────
        d["status"] = "building"
        safe_name = "".join(c if c.isalnum() or c == "-" else "-" for c in project_name.lower())
        image_tag = f"deployai-{safe_name}-{deployment_id[:8]}"
        log(deployment_id, f"🔨 Building Docker image: {image_tag}")

        build_proc = subprocess.Popen(
            ["docker", "build", "--no-cache", "-t", image_tag, "."],
            cwd=str(repo_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr → stdout so we see all errors
            text=True,
            bufsize=1,
        )

        build_output_lines = []
        for raw_line in build_proc.stdout:
            line = raw_line.rstrip()
            if line:
                build_output_lines.append(line)
                log(deployment_id, f"  {line}")

        build_proc.wait()

        if build_proc.returncode != 0:
            # Surface the last 20 lines so users can diagnose without digging
            tail = build_output_lines[-20:] if len(build_output_lines) > 20 else build_output_lines
            error_summary = "\n".join(tail)
            log(deployment_id, "❌ Docker build failed — see lines above for the root cause", "error")
            d["status"] = "failed"
            d["error"] = f"Docker build failed (exit {build_proc.returncode}).\n\nLast output:\n{error_summary}"
            return

        log(deployment_id, "✅ Docker image built successfully")
        d["image_tag"] = image_tag

        # Phase 5: Run Container (with port-conflict retry)
        d["status"] = "deploying"
        internal_port = stack["internal_port"]
        safe_proj = "".join(c if c.isalnum() or c == "-" else "-" for c in project_name.lower())
        container_name = f"deployai-{safe_proj}-{deployment_id[:8]}"

        container_id = None
        external_port = None
        MAX_PORT_RETRIES = 5

        for attempt in range(1, MAX_PORT_RETRIES + 1):
            external_port = find_free_port()
            log(deployment_id, f"\U0001f680 Port attempt {attempt}: {external_port} (host) -> {internal_port} (container)")

            # Remove any leftover container with the same name from prior crash
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

            run_result = subprocess.run(
                [
                    "docker", "run", "-d",
                    "--name", container_name,
                    "-p", f"{external_port}:{internal_port}",
                    "--restart", "unless-stopped",
                    "--label", f"deployai.project={project_name}",
                    "--label", f"deployai.id={deployment_id}",
                    image_tag,
                ],
                capture_output=True, text=True,
            )

            if run_result.returncode == 0:
                container_id = run_result.stdout.strip()[:12]
                log(deployment_id, f"\u2705 Container started: {container_id}")
                break

            err = run_result.stderr.strip()
            if "port is already allocated" in err or "address already in use" in err:
                log(deployment_id, f"\u26a0\ufe0f  Port {external_port} already in use — retrying...", "warning")
                continue

            # Any other docker run error is fatal
            log(deployment_id, f"\u274c Container failed to start: {err}", "error")
            d["status"] = "failed"
            d["error"] = f"Container start failed:\n{err}"
            return

        if container_id is None:
            log(deployment_id, f"\u274c Could not find a free port after {MAX_PORT_RETRIES} attempts", "error")
            d["status"] = "failed"
            d["error"] = f"Port allocation exhausted after {MAX_PORT_RETRIES} retries. Too many containers running?"
            return

        # Detect server public IP
        try:
            ip_result = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
            server_ip = ip_result.stdout.strip().split()[0]
        except Exception:
            server_ip = "localhost"

        public_url = f"http://{server_ip}:{external_port}"
        log(deployment_id, f"🌐 Deployment live!")
        log(deployment_id, f"🔗 URL: {public_url}")

        d["status"] = "running"
        d["public_url"] = public_url
        d["container_name"] = container_name
        d["container_id"] = container_id
        d["external_port"] = external_port
        d["internal_port"] = internal_port

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        log(deployment_id, f"❌ Unexpected error: {e}", "error")
        print(tb, flush=True)
        d["status"] = "failed"
        d["error"] = f"Unexpected error: {e}"
    finally:
        # Always clean up the cloned source — the Docker image is already built
        if repo_path.exists():
            try:
                shutil.rmtree(str(repo_path))
            except Exception:
                pass

# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "DeployAI Platform", "version": "1.1.0", "status": "running"}

@app.get("/api/health")
def health():
    docker_ok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    return {
        "status": "healthy",
        "docker": "available" if docker_ok else "unavailable",
        "active": sum(1 for d in deployments.values() if d["status"] == "running"),
    }

@app.post("/api/deploy")
async def deploy(req: DeployRequest, background_tasks: BackgroundTasks):
    if not req.project_name.strip():
        raise HTTPException(400, "project_name is required")
    if not req.repo_url.strip().startswith("http"):
        raise HTTPException(400, "repo_url must be a valid http/https URL")

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
        "image_tag": None,
        "container_id": None,
        "container_name": None,
        "external_port": None,
        "internal_port": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
    }
    background_tasks.add_task(
        run_deployment,
        deployment_id,
        req.project_name.strip(),
        req.repo_url.strip(),
        req.ai_api_key or "",
        req.ai_provider or "groq",
    )
    return {"deployment_id": deployment_id, "status": "queued"}

@app.get("/api/deployments")
def list_deployments():
    return [
        {
            "id": d["id"],
            "project_name": d["project_name"],
            "status": d["status"],
            "public_url": d["public_url"],
            "created_at": d["created_at"],
        }
        for d in deployments.values()
    ]

@app.get("/api/deployments/{deployment_id}")
def get_deployment(deployment_id: str):
    if deployment_id not in deployments:
        raise HTTPException(404, "Deployment not found")
    return deployments[deployment_id]

@app.get("/api/deployments/{deployment_id}/logs")
def get_logs(deployment_id: str, since: int = 0):
    if deployment_id not in deployments:
        raise HTTPException(404, "Deployment not found")
    d = deployments[deployment_id]
    return {
        "logs": d["logs"][since:],
        "total": len(d["logs"]),
        "status": d["status"],
    }

@app.delete("/api/deployments/{deployment_id}")
def delete_deployment(deployment_id: str):
    if deployment_id not in deployments:
        raise HTTPException(404, "Deployment not found")
    d = deployments[deployment_id]
    for cmd in [
        ["docker", "stop", d.get("container_name", "")],
        ["docker", "rm",   d.get("container_name", "")],
        ["docker", "rmi",  d.get("image_tag", "")],
    ]:
        if cmd[-1]:
            subprocess.run(cmd, capture_output=True)
    del deployments[deployment_id]
    return {"status": "deleted"}
