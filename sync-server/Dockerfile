FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY server.py .
VOLUME ["/data"]
EXPOSE 7000
CMD ["gunicorn", "--bind", "0.0.0.0:7000", "--workers", "2", "server:app"]
