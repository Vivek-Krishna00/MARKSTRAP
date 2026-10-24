FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY engine ./engine
RUN pip install --no-cache-dir .
COPY audience ./audience
RUN pip install --no-cache-dir uv && uv venv -p 3.11 audience/.venv \
    && uv pip install --no-cache -p audience/.venv/bin/python -r audience/requirements.txt
COPY config.yaml ./
COPY web ./web
ENV DB_PATH=/app/data/engine.db
EXPOSE 8000
CMD ["uvicorn", "engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
