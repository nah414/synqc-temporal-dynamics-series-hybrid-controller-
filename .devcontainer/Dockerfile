FROM mcr.microsoft.com/devcontainers/python:3.12

# Pre-cache wheels for faster, repeatable installs (useful behind proxies).
COPY backend/requirements.lock /tmp/requirements.lock
RUN python -m pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /usr/local/share/pip-wheels -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock
