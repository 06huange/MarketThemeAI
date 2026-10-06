# Weekly pipeline: BigQuery query -> article download -> embeddings -> themes -> export.
# Runs as a scheduled ECS Fargate task; state lives in S3 (see src/storage.py).

FROM python:3.11-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
COPY requirements.txt .
# CPU-only torch: the default index ships CUDA builds that add several GB.
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

FROM python:3.11-slim
COPY --from=build /venv /venv
ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1
# Bake the embedding model into the image so runs don't depend on Hugging Face.
RUN HF_HUB_OFFLINE=0 python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

WORKDIR /app
COPY data/company_universe.csv data/
COPY src/ src/
RUN useradd --create-home pipeline && chown -R pipeline /app
USER pipeline

ENTRYPOINT ["python", "-m", "src.pipeline"]
