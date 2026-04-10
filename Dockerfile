FROM node:24-slim AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm install
COPY web/ ./
ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
ARG VITE_AUTH0_AUDIENCE
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .

COPY --from=frontend /app/web/dist web/dist

ENV WEB_DIST_DIR=/app/web/dist

EXPOSE 8000

CMD uvicorn realestate.api:app --host 0.0.0.0 --port ${PORT:-8000}
