FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock
COPY app.py .
COPY static/ static/
COPY templates/ templates/
RUN useradd -m appuser
USER appuser
ENV HOST=0.0.0.0
CMD ["python", "app.py"]
