FROM ubuntu:22.04

RUN apt update && apt install -y --no-install-recommends \
	gzip \
	curl \
	wget \
	python3 \
	python3-pip \
	python-is-python3

RUN pip3 install pulsar-client

RUN pip3 install --upgrade pip &&     pip3 install galaxy-app &&     pip3 install galaxy-tool-util &&     pip3 install galaxy-util &&     pip3 install requests &&     pip3 install requests-toolbelt &&     pip3 install pulsar-galaxy-lib

# Required by mamba
RUN apt install -y --no-install-recommends \
	libarchive13

RUN cd /tmp && \
	wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && \
	bash Miniconda3-latest-Linux-x86_64.sh -b -p "/opt/miniconda3"

RUN /opt/miniconda3/bin/conda install -c conda-forge mamba
ENV PATH="/opt/miniconda3/bin/:${PATH}"

RUN mamba create -n "__fastqc@0.11.9" -c bioconda fastqc=0.11.9 -y
#RUN mamba install -c bioconda fastqc -y

RUN mkdir -p /home/ubuntu/galaxy/database/dependencies/
RUN ln -s /opt/miniconda3 /home/ubuntu/galaxy/database/dependencies/_conda

COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
#ENTRYPOINT ["sleep", "infinity"]

