FROM ubuntu

ENV DEBIAN_FRONTEND noninteractive
RUN apt update && apt install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        nmap \
        vim \
        s3cmd \
        lftp

COPY .s3cfg /root/

ENTRYPOINT ["sleep", "infinity"]
