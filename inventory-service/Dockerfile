FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
