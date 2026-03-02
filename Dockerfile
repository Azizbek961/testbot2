FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# (ixtiyoriy) ba'zi paketlar kompilyatsiya talab qilsa
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bot long-polling bo'lsa shunchaki ishga tushiramiz
CMD ["python", "-u", "main.py"]