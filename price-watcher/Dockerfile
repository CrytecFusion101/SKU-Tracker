# Base image already bundles Chromium + all OS-level dependencies Playwright
# needs, matched to the playwright pip version pinned in requirements.txt.
# This avoids relying on Railway's Nixpacks builder to run
# `playwright install --with-deps`, which needs apt privileges it may not have.
FROM mcr.microsoft.com/playwright/python:v1.61.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "tracker.py"]
