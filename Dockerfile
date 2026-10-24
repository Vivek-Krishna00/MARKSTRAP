FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY engine ./engine
RUN pip install --no-cache-dir .
COPY config.yaml ./
COPY web ./web
ENV DB_PATH=/app/data/engine.db
EXPOSE 8000
CMD ["uvicorn", "engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
