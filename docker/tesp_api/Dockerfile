# Uses multi-stage builds requiring Docker 17.05 or higher
# See https://docs.docker.com/develop/develop-images/multistage-build/

# Environment variables and base image
FROM python:3.10-slim-buster as python-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"


# Builder is used to install shared depenedencies
FROM python-base as builder
RUN buildDeps="build-essential" \
    && apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && apt-get install -y --no-install-recommends $buildDeps \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
ENV POETRY_VERSION=1.1.13
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy python requirements and install runtime deps
WORKDIR $PYSETUP_PATH
#COPY ./poetry.lock ./pyproject.toml ./
COPY ./pyproject.toml ./
RUN poetry install --no-dev


# Development installs all dependencies and can be used
# to develope code. With local volume mapeed under /app
# hot reloading (change code in running app) can be used
FROM python-base as development
ENV FASTAPI_PROFILE=dev-docker

COPY --from=builder $POETRY_HOME $POETRY_HOME
COPY --from=builder $PYSETUP_PATH $PYSETUP_PATH

WORKDIR $PYSETUP_PATH
RUN poetry install
WORKDIR /app
COPY . .

EXPOSE 8080
CMD ["uvicorn", "--reload", "--host=0.0.0.0", "--port=8080", "tesp_api.tesp_api:app"]