# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps (psycopg2 etc uchun)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# install python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# copy project
COPY . /app

# collectstatic uchun (agar STATIC ishlatsangiz)
# RUN python manage.py collectstatic --noinput

EXPOSE 8080

# Gunicorn (Django production)
# IMPORTANT: myproject.wsgi ni o'zingizning project nomingizga almashtiring
CMD ["gunicorn", "myproject.wsgi:application", "--bind", "0.0.0.0:8080"]