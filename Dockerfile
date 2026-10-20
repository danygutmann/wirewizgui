FROM node:24-alpine AS frontend-build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
COPY vite.config.js ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_MODE=production \
    DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY run.py ./
COPY wireviz_gui ./wireviz_gui
COPY --from=frontend-build /build/wireviz_gui/static/dist ./wireviz_gui/static/dist
RUN useradd --system --uid 10001 --create-home wireviz \
    && mkdir -p /data/projects /data/templates /data/config \
    && chown -R wireviz:wireviz /data
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()"
CMD ["gunicorn", "--bind=0.0.0.0:8080", "--workers=2", "--timeout=60", "run:app"]
