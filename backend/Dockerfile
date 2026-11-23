FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini worker.py ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN useradd --uid 10001 washslot && install -d -o washslot -g washslot /app/keys
USER washslot
