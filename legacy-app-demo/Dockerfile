FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock
COPY app.py gunicorn.conf.py ./
RUN useradd -m appuser
USER appuser
ENV HOST=0.0.0.0
# Gunicorn lee gunicorn.conf.py (puerto, hilos, registros).
CMD ["gunicorn", "app:app"]
