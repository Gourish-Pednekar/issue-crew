FROM python:3.11-slim

# Tests run inside this image; dependencies are installed now so the
# container can run later with no network access at all.
RUN pip install --no-cache-dir fastapi httpx pytest

# Don't write .pyc files into the mounted project folder.
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace