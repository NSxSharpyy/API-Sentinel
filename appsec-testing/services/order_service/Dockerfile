FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser
USER appuser

ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0

CMD ["python", "app.py"]
