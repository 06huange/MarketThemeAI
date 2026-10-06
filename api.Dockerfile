# Read API. A plain uvicorn server: runs as-is with `docker run`, and on AWS Lambda
# through the Lambda Web Adapter extension, which forwards Lambda events to it.

FROM python:3.11-slim
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health
WORKDIR /app
COPY api/requirements.txt api/
RUN pip install --no-cache-dir -r api/requirements.txt
COPY api/ api/
RUN useradd --create-home api
USER api

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
