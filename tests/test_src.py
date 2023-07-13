#from starlette.testclient import TestClient

import time
import requests
import json

import sys
sys.path.append('/app')

from tesp_api import __version__
from tesp_api.tesp_api import app

base_url = "http://localhost:8080"
#client = TestClient(app, base_url=base_url)

def _gnv(data, key):
    """Get a nested value from a dictionary using dot notation."""
    keys = key.split(".")
    current_data = data
    for k in keys:
        try:
            current_data = current_data[k]
        except KeyError:
            return False
    return current_data

def _get_request(url):
    """Sent a GET HTTP request, test the status, jsonization and return the response in JSON."""
    #return client.get(url)
    #return requests.get(f"{base_url}{url}")
    resp = requests.get(f"{base_url}{url}")
    assert resp.status_code == 200
    assert resp.json()
    return resp.json()

def _post_request(url, payload):
    """Sent a POST HTTP request, test the status, jsonization and return the response in JSON."""
    #return client.get(url)
    #return requests.get(f"{base_url}{url}")
    resp = requests.post(f"{base_url}{url}", json=payload)
    assert resp.status_code == 200
    assert resp.json()
    return resp.json()

def _open_json(filename):
    with open(f"tests/test_jsons/{filename}", 'r') as f:
        data = f.read()
    return json.loads(data)

def _wait_for_state(id, state, timeout = 10):
    for i in range(timeout):
        resp = _get_request(f"/v1/tasks/{id}")
        s = _gnv(resp, "state")
        
        # end on right state
        if s == state:
            return resp
        
        # raise exception on wrong state (not right state and not RUNNING state)
        if s != "INITIALIZING" and s != "QUEUED" and s != "RUNNING":
            raise Exception(f"_wait_for_state(): unexpected state. Expected: {state}, given: {s}")
        
        time.sleep(1)
        
    raise Exception("_wait_for_state(): timeout")


def test_version():
    assert __version__ == '0.0.1'

def test_service_info():
    data = _get_request("/v1/service-info")

    assert _gnv(data, "id")
    assert _gnv(data, "name")
    assert _gnv(data, "type.group") == "org.ga4gh"
    assert _gnv(data, "type.artifact") == "tes"
    assert _gnv(data, "type.version") == "1.0.0"
    assert _gnv(data, "organization.name")
    assert _gnv(data, "organization.url")
    assert _gnv(data, "version")

def test_test_info():
    data = _get_request("/v1/test-info")

    assert _gnv(data, "asdf") == "asdf"

def test_empty_task_list():
    data = _get_request("/v1/tasks")

    tasks = _gnv(data, "tasks")
    assert tasks
    assert isinstance(tasks, list)

def _test_submit_task_complete():
    # submit task
    json = _open_json("01_state_true.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    time.sleep(10)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "RUNNING"

    time.sleep(30)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "COMPLETE"

def _test_submit_task_fail():
    # submit task
    json = _open_json("02_state_false.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    time.sleep(10)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "RUNNING"

    time.sleep(30)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "EXECUTOR_ERROR"

def _test_submit_task_multi_complete():
    # submit task
    json = _open_json("03-multi_true.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    time.sleep(10)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "RUNNING"

    time.sleep(30)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "COMPLETE"

def _test_submit_task_multi_fail_1():
    # submit task
    json = _open_json("03-multi_false_1.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    time.sleep(10)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "RUNNING"

    time.sleep(30)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "EXECUTOR_ERROR"

def _test_submit_task_multi_fail_2():
    # submit task
    json = _open_json("03-multi_false_2.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    time.sleep(10)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "RUNNING"

    time.sleep(30)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "EXECUTOR_ERROR"

def _test_submit_task_multi_fail_3():
    # submit task
    json = _open_json("03-multi_false_3.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    time.sleep(10)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "RUNNING"

    time.sleep(30)

    # try to get status of the task
    resp = _get_request(f"/v1/tasks/{id}")
    assert _gnv(resp, "state") == "EXECUTOR_ERROR"

def test_inputs():
    # submit task
    json = _open_json("04-inputs.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    assert _wait_for_state(id, "COMPLETE", 30)

def test_volumes():
    # submit task
    json = _open_json("06-volumes.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    assert _wait_for_state(id, "COMPLETE", 30)

def test_envs():
    # submit task
    json = _open_json("envs.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    assert _wait_for_state(id, "COMPLETE", 30)

def test_workdir():
    # submit task
    json = _open_json("workdir.json")
    resp = _post_request("/v1/tasks", payload=json)

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    assert _wait_for_state(id, "COMPLETE", 30)


