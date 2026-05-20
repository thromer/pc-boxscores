# Build

# We use the same image as the runtime base image so that Python
# version and location matches.
ARG BASE_IMAGE=scratch
FROM ${BASE_IMAGE} AS builder
ARG PYVER

WORKDIR /pip
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --prefix=python-packages -r requirements.txt && \
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
