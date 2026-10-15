FROM python:3.12-slim
WORKDIR /app

# Dependencies first so a model or source change reuses the cached layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The trained bundle ships with the image: app.py resolves it relative to
# its own location and refuses to start without it (fail-closed).
COPY . .

EXPOSE 8001

# ONE worker is deliberate. The loaded hybrid bundle occupies ~184 MB RSS per
# worker (measured), so a 512 MB instance holds exactly one. Raise WEB_CONCURRENCY
# only on an instance with >= 256 MB of headroom per additional worker.
ENV WEB_CONCURRENCY=1
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${WEB_CONCURRENCY}"]
