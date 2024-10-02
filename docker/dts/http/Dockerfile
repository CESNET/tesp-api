FROM ubuntu:jammy
# target-image-suffix: tools/http-storage:0.1

COPY requirements.txt ./
COPY main_flask.py logger_config.py ./
COPY docker-entrypoint.sh /

RUN apt update && apt install -y --no-install-recommends \
	python3 \
	python3-pip \
	&& pip3 install -r requirements.txt \
	&& chmod +x /docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/docker-entrypoint.sh"]
