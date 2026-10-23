# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG API_INTERNAL_URL=http://api:6200
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN npm run build

FROM node:22-bookworm-slim AS web
WORKDIR /app
ENV NODE_ENV=production
ENV API_INTERNAL_URL=http://api:6200
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY --from=web-build /app/web/.next ./.next
COPY --from=web-build /app/web/public ./public
COPY web/next.config.ts ./next.config.ts
EXPOSE 6108
CMD ["npx", "next", "start", "-p", "6108"]

FROM python:3.13-slim AS api
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
COPY pyproject.toml README.md ./
COPY softwiki ./softwiki
RUN pip install -e .
EXPOSE 6200 6100
CMD ["python", "-m", "softwiki.cli.main", "api", "--host", "0.0.0.0", "--port", "6200"]
