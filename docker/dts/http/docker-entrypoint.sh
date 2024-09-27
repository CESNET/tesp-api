#!/bin/sh

#cd "$NAME" && uvicorn main:app --host 0.0.0.0 --port 8000
cd "$NAME" && python3 main_flask.py

