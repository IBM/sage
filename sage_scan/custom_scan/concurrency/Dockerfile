FROM python:3.11-buster

WORKDIR /root

ENV POETRY_HOME="/opt/poetry" \
    POETRY_VERSION=1.5.1
ENV PATH="$POETRY_HOME/bin::$PATH"

COPY poetry.lock pyproject.toml ./

RUN apt-get clean && apt-get update && \
    apt-get install -y sudo && \
    pip install -U pip && \
    pip install git+https://github.com/IBM/sage.git@4456c63f02d9f4db5a4fca1386cb12f4e103ea25 && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

RUN celery --version

COPY . /root/

RUN rm -rf /var/cache/apk/*
EXPOSE 5000