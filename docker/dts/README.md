The `docker-compose.yaml` file in this directory is primarily intended for testing the DTS services of the TESP API. Smoke tests exercise **only the HTTP service**.
To ensure proper execution of the tests, run `docker-compose.yaml` both in this directory and in the `/tesp-api` directory with:
```
docker compose up -d --build
```
# DTS

Example of data transfer server using HTTP, S3 and FTP.

### Current status

- HTTP is the only DTS service implemented in this repository and used by smoke tests.
- S3 runs MinIO as an external service for manual testing.
- FTP runs the upstream `ftpserver` container and uses S3 (MinIO) as its storage backend.

`docker-compose.yaml` deploys 4 containers:  
- s3
- ftp
- http
- clients

The `clients` container contains clients for the used protocols, so you do not need to install the clients on your local computer to test it.


## Deploy

`docker compose up -d`

## Examples of usage

### HTTP

The HTTP service provides multiple routes:

**Upload** (saves to `/data/uploaded_data/`)  
`curl -i -X POST -F "file=@up-file.txt" localhost:5000/upload`

**Download (legacy route)**  
`curl -X GET -o down-file.txt localhost:5000/download/file.txt`

**Browse test_data (smoke test compatible)**  
`curl localhost:5000/test_data/test.txt`  
`curl localhost:5000/test_data/input_dir/`

**List all files**  
`curl localhost:5000/list`

### S3
Create bucket  
`s3cmd mb s3://test`

Upload  
`s3cmd put up-file.txt s3://test/file.txt`

Download  
`s3cmd get s3://test/file.txt file.txt`

or more complex scenario

```
# create the target bucket
TARGET_BUCKET=test1234
s3cmd mb s3://${TARGET_BUCKET}

# create samples in target bucket
N_SAMPLES=10
for i in $(seq 1 $N_SAMPLES); do
  TEMPFILE=$(mktemp) && echo "hello world !!! ($i)" > $TEMPFILE
  s3cmd put $TEMPFILE s3://${TARGET_BUCKET}/sample_${i} 
done

# list the bucket content of the target bucket
s3cmd ls s3://${TARGET_BUCKET}

LOCAL_DIR=/tmp/downloaded_samples && mkdir $LOCAL_DIR

for i in $(seq 1 $N_SAMPLES); do
  s3cmd get s3://${TARGET_BUCKET}/sample_${i} $LOCAL_DIR 
done

s3cmd rm --recursive --force s3://${TARGET_BUCKET}
```

List all object in all buckets  
`s3cmd la`

### FTP


Get some data
```
SAMPLE_DATE=/tmp/sample.jpg
curl -o /tmp/sample.jpg https://github.blog/wp-content/uploads/2024/07/github-logo.png
```

#### Access via FTP

Upload and download data
```
lftp -p 2121 -e "put /tmp/sample.jpg; get $(basename $SAMPLE_DATE) -o /tmp/sample_back.jpg; bye" service-ftp
```

#### Access via HTTP

##### Upload

POST to `http://localhost:5000/upload` with file as multipart form data:
```bash
curl -F "file=@/tmp/qwerty" http://localhost:5000/upload
```

With subdirectory:
```bash
curl -F "file=@/tmp/qwerty" http://localhost:5000/upload/foo/bar
```

##### Download

Legacy route:
```bash
wget http://localhost:5000/download/foo/bar/qwerty
```

Smoke test compatible route (serves from mounted test_data):
```bash
curl http://localhost:5000/test_data/test.txt
```

##### List of all data

```bash
curl http://localhost:5000/list
```
