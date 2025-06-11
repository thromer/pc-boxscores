# Build

# We use the same image as the runtime base image so that Python
# version and location matches.
FROM us-west1-docker.pkg.dev/serverless-runtimes/google-22/runtimes/python312 AS builder

WORKDIR /pip
COPY requirements.txt .
# Needed for gcloud builds submit with gcr.io/cloud-builders/docker (default)
# USER root
RUN python -m pip install --no-cache-dir --prefix=python-packages -r requirements.txt && \
    PYTHONPATH=python-packages/lib/python3.12/site-packages python -m pip freeze

# Run
FROM scratch
COPY --from=builder /pip/python-packages /opt/python
COPY --chown=33:33 . /workspace/

USER www-data

ENV PYTHONPATH=/opt/python/lib/python3.12/site-packages
ENV PATH=/opt/python/bin:$PATH

WORKDIR /workspace

CMD ["python", "start.py"]
