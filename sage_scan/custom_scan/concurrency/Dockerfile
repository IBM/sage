FROM python:3.11-buster

ARG GIT_ACCESS_TOKEN

WORKDIR /root

ENV POETRY_HOME="/opt/poetry" \
    POETRY_VERSION=1.5.1
ENV PATH="$POETRY_HOME/bin::$PATH"

COPY poetry.lock pyproject.toml ./

RUN apt-get clean && apt-get update && \
    apt-get install -y sudo && \
    pip install -U pip && \
    git config --global url."https://${GIT_ACCESS_TOKEN}@github.ibm.com".insteadOf "ssh://git@github.ibm.com" && \
    pip install git+ssh://git@github.ibm.com/ansible-risk-insight/sage.git@bbecdf379c8b96ab4ac44ab4836fe01e04de796c && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

RUN celery --version

COPY . /root/

RUN rm -rf /var/cache/apk/*
EXPOSE 5000