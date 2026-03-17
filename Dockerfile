# ─── Stage 1: Build React frontend ──────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

# Copy package files
COPY frontend/package*.json ./

RUN npm ci --legacy-peer-deps

# Copy source
COPY frontend/ .

# Build (outputs to /frontend/dist)
RUN npm run build

# ─── Stage 2: Python backend + static frontend ───────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ .

# Copy compiled frontend into Flask static folder
COPY --from=frontend-build /frontend/dist ./static

# Flask will serve the React app from /static
# We patch main.py to also serve index.html for all non-API routes
COPY serve_static.py .

EXPOSE 8080
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "serve_static:app"]
