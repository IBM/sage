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
    pip install git+https://github.com/IBM/sage.git@178ef128803bd63f54a11b0efb114dad047b558e && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

RUN celery --version

COPY . /root/

RUN rm -rf /var/cache/apk/*
EXPOSE 5000