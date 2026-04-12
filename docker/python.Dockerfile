FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY configs ./configs
COPY migrations ./migrations
COPY src ./src

RUN pip install --upgrade pip setuptools wheel \
    && pip install .

EXPOSE 8000
