# Uses multi-stage builds requiring Docker 17.05 or higher
# See https://docs.docker.com/develop/develop-images/multistage-build/

# Environment variables and base image
FROM python:3.9-slim-bullseye as python-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

ENV PATH="$VENV_PATH/bin:$PATH"


# Builder is used to install shared depenedencies
FROM python-base as builder
WORKDIR $PYSETUP_PATH
RUN python3 -m venv $VENV_PATH && . .venv/bin/activate
RUN pip install 'pulsar-app[web]'


# Development installs all dependencies and can be used
# to develope code.
FROM python-base as development
COPY --from=builder $PYSETUP_PATH $PYSETUP_PATH

RUN apt-get update && apt-get install -y curl gnupg-agent software-properties-common lsb-release
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | apt-key add -
RUN add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/debian $(lsb_release -cs) stable"
RUN apt-get update
RUN apt-get install -y docker-ce docker-ce-cli containerd.io
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR $PYSETUP_PATH
COPY startup.sh startup.sh
RUN pulsar-config --host 0.0.0.0
EXPOSE 8913
CMD ["/bin/bash", "./startup.sh"]
