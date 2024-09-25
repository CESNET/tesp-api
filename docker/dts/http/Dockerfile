FROM ubuntu:22.04

ARG NAME=nginx-http-test

RUN apt update && apt install -y --no-install-recommends \
	python3 \
	python3-pip

RUN mkdir /opt/${NAME}
WORKDIR /opt/${NAME}

COPY requirements.txt ./

RUN pip3 install -r requirements.txt

COPY main_flask.py ./
COPY main_fastapi.py ./

COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
