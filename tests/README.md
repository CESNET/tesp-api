# Testing

Integration tests for TESP-API. All tests run against a live TESP-API instance at `http://localhost:8080`.

## Prerequisites

Start TESP-API + MongoDB + Pulsar from the project root:

```bash
docker compose --profile pulsar up -d --build
```

## Running Tests

### 1. Start the upload server

For I/O tests (`test_inputs`, `test_dir_input`, `test_volumes`, `test_envs`), the test fixtures download/upload files via HTTP. Start the local file server:

```bash
python3 tests/upload_server.py
```

This serves `tests/test_data/` on port 5000 and accepts uploads to `tests/uploaded_data/`.

### 2. Run smoke tests

```bash
python3 -m pytest tests/smoke_tests.py -v
```

### Load/stress test (100 concurrent tasks)

```bash
python3 -m pytest tests/load_stress_test.py -v
```

## Platform Notes

The test fixtures use `http://172.17.0.1:5000` to reach the host from inside containers. This works on **Linux** (Docker bridge gateway IP).


## Test Fixtures

All task JSON fixtures are in `test_jsons/`. Key files:

| Fixture | Description | Requires upload_server |
|---|---|---|
| `state_true.json` | Simple task that should succeed | No |
| `state_false.json` | Task designed to fail | No |
| `cancel.json` | Long-running task (`sleep infinity`) for cancellation | No |
| `multi_true.json` | Three sequential executors | No |
| `inputs.json` | HTTP download + inline content | **Yes** |
| `dir-io.json` | Directory input/output via HTTP | **Yes** |
| `volumes.json` | Shared volume between executors | **Yes** |
| `envs.json` | Environment variables with output upload | **Yes** |
| `workdir.json` | Working directory test | No |

## DTS (Data Transfer Services)

The `docker/dts/` directory contains an **alternative** test infrastructure with MinIO (S3), FTP, and HTTP services running in containers. At the moment, only HTTP service is compatible with the smoke tests.

### Using DTS instead of upload_server.py

```bash
# Start DTS (from project root)
cd docker/dts && docker compose up -d --build && cd ../..

# Run tests (DTS serves on the same port 5000)
python3 -m pytest tests/smoke_tests.py -v
```

DTS mounts `tests/test_data/` and `tests/uploaded_data/` so the same fixture URLs work.

## Cleanup

The test suite automatically cleans up:
- `uploaded_data/` directory created by upload tests
- Leftover Ubuntu containers from failed tests
