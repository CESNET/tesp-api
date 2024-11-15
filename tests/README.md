# Testing
To test functionality of TESP API, running `docker-compose.yaml` with: 
```
docker compose up -d --build  
```
is necessary both in `/tesp-api` and `/tesp-api/docker/dts`
Tests themselves can be run with:
```
python3 -m pytest smoke_tests.py
```
