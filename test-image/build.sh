#!/bin/bash

IMAGE="tesp-test-image"

docker build -t hub.cerit.io/josef_handl/${IMAGE} .
docker push hub.cerit.io/josef_handl/${IMAGE}

