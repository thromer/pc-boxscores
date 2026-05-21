# Build

# We use the same image as the runtime base image so that Python
# version and location matches.
ARG BASE_IMAGE=scratch
FROM ${BASE_IMAGE} AS builder
ARG PYVER

COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /usr/local/bin/uv

WORKDIR /pip
COPY pyproject.toml uv.lock .

ENV UV_NO_MANAGED_PYTHON=1
RUN uv --no-cache export --frozen --no-default-groups -o requirements.txt && \
    uv pip install --no-cache-dir --prefix=python-packages --no-python-downloads --require-hashes -r requirements.txt && \
    PYTHONPATH=python-packages/lib/python${PYVER}/site-packages python -m pip freeze --no-cache-dir

# Run
FROM scratch
ARG PYVER

COPY --from=builder /pip/python-packages /opt/python
COPY --chown=33:33 . /workspace/

USER www-data

ENV PYTHONPATH=/opt/python/lib/python${PYVER}/site-packages
ENV PATH=/opt/python/bin:$PATH

WORKDIR /workspace

CMD ["python", "start.py"]
