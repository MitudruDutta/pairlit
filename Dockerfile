FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir .
COPY --from=web /web/out ./apps/web/out
RUN mkdir -p data/private
EXPOSE 8000
CMD ["uvicorn", "pairlit.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
