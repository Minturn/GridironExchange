# One image: build the frontend, serve everything from FastAPI on :8200.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary
COPY backend/ ./
COPY --from=ui /ui/dist ./frontend-dist
ENV GRIDX_STATIC_DIR=./frontend-dist
EXPOSE 8200
# migrations run on boot — idempotent, and Fly release_command also covers it
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8200"]
