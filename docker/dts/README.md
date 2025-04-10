The `docker-compose.yaml` file in this directory is primarily intended for testing the DTS services of the TESP API.
To ensure proper execution of the tests, run `docker-compose.yaml` both in this directory and in the `/tesp-api` directory with:
```
docker compose up -d --build
```

# DTS

Example of data transfer server using HTTP, S3 and FTP.

Project uses Docker and deploy 4 containers:  
- s3
- ftp
- http
- clients

The `clients` container contains clients for the used protocols. So you doesn't need to install the clients on you local computer to test it.

## Deploy

`docker compose up -d`

## Examples of usage

### HTTP

Upload  
`curl -i -X POST -F "file=@up-file.txt;filename=file.txt" service-http:5000/upload`

Download  
`curl -X GET -o down-file.txt service-http:5000/download/file.txt`

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

POST + `http://localhost:5000/upload` while payload is sent as 'file' HTTP body parameter.
```
curl -F "file=@/tmp/qwerty" http://localhost:5000/upload/foo/bar
```


##### Download
GET  + `http://localhost:5000/download` while payload is sent as 'file' HTTP body parameter.
```
wget  http://localhost:5000/download/foo/bar/qwerty
```



##### List of all data
GET  + `http://localhost:5000/list` 
