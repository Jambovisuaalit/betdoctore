FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
COPY alembic.ini ./
COPY migrations ./migrations
USER 65534:65534
CMD ["uvicorn", "betdoctore.api:app", "--host", "0.0.0.0", "--port", "8000"]
