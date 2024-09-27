
import time
import requests
import json
import os

import sys
sys.path.append('/app')

from tesp_api.utils.commons import Commons

base_url = "http://localhost:8080"

script_directory = os.path.dirname(os.path.abspath(__file__))


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
    resp = requests.get(f"{base_url}{url}")
    assert resp.status_code == 200
    assert resp.json()
    return resp.json()

def _post_request(url, payload={}):
    """Sent a POST HTTP request, test the status, jsonization and return the response in JSON."""
    resp = requests.post(f"{base_url}{url}", json=payload)
    assert resp.status_code == 200
    assert resp
    return resp

def _open_json(filename):
    with open(f"{script_directory}/test_jsons/{filename}", 'r') as f:
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
            raise Exception(f"_wait_for_state(): unexpected state. ID: {id}, expected: {state}, given: {s}")
        
        time.sleep(1)
        
    raise Exception(f"_wait_for_state(): timeout. ID: {id}, state: {s}")

def _test_simple(json, timeout, state = 'COMPLETE'):
    # submit task
    json = _open_json(json)
    resp = _post_request("/v1/tasks", payload=json).json()

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    return _wait_for_state(id, state, timeout)

def _test_activity(json, timeout_running, timeout_complete, state = 'COMPLETE'):
    # submit task
    json = _open_json(json)
    resp = _post_request("/v1/tasks", payload=json).json()

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    if not _wait_for_state(id, 'RUNNING', timeout_running):
        return False
    return _wait_for_state(id, state, timeout_complete)

def _test_sequence_simple(jsons, timeout, state = 'COMPLETE'):
    for file_name in jsons:
        json = f'{file_name}.json'
        if not _test_simple(json, timeout, state):
            return False

    return True

def _test_sequence_activity(jsons, timeout_running, timeout_complete, state = 'COMPLETE'):
    for file_name in jsons:
        json = f'{file_name}.json'
        if not _test_activity(json, timeout_running, timeout_complete, state):
            return False

    return True

def test_service_info():
    data = _get_request("/v1/service-info")    

    # see https://github.com/ga4gh/task-execution-schemas/releases
    TES_API_VERSION = '1.0.0'
    
    assert _gnv(data, "id")
    assert _gnv(data, "name")
    assert _gnv(data, "type.group") == "org.ga4gh"
    assert _gnv(data, "type.artifact") == "tes"
    assert _gnv(data, "type.version") == TES_API_VERSION
    assert _gnv(data, "organization.name")
    assert _gnv(data, "organization.url")
    assert _gnv(data, "version") == Commons.get_service_version()

def test_submit_task_complete():
    assert _test_activity("state_true.json", 10, 60, 'COMPLETE')

def test_submit_task_fail():
    assert _test_activity("state_false.json", 10, 60, 'EXECUTOR_ERROR')

def test_submit_task_multi_complete():
    assert _test_activity("multi_true.json", 10, 60, 'COMPLETE')

def test_submit_task_multi_fail():
    jsons = ["multi_false_1", "multi_false_2", "multi_false_3"]
    assert _test_sequence_activity(jsons, 10, 60, 'EXECUTOR_ERROR')

def test_get_task_list():
    data = _get_request("/v1/tasks")

    tasks = _gnv(data, "tasks")
    assert tasks
    assert isinstance(tasks, list)

def test_inputs():
    # Tests only HTTP download for now, and direct input.
    assert _test_simple("inputs.json", 120)

#def test_outputs():
    # Tests S3 and FTP upload and download.
    #jsons = ["outputs-prepare", "outputs-prepare-check", "outputs-test", "outputs-test-check"]
    #assert _test_sequence_simple(jsons, 180)

def test_volumes():
    assert _test_simple("volumes.json", 60)

def test_envs():
    assert _test_simple("envs.json", 60)

def test_workdir():
    assert _test_simple("workdir.json", 120)

#def test_stdin():
    #jsons = ['stdin-prepare', 'stdin-test']
    #assert _test_sequence_simple(jsons, 120)

#def test_stdout():
    #jsons = ['std-prepare-1', 'std-prepare-2', 'stdout-test-1', 'stdout-test-2', 'stdout-check']
    #assert _test_sequence_simple(jsons, 180)

#def test_stderr():
    #jsons = ['std-prepare-1', 'std-prepare-2', 'stderr-test-1', 'stderr-test-2', 'stderr-check']
    #assert _test_sequence_simple(jsons, 180)

def test_task_cancel():
    response = _test_simple("cancel.json", 60, "RUNNING")
    task_id = _gnv(response, "id")
    assert task_id
    _post_request(f"/v1/tasks/{task_id}:cancel")
    assert _wait_for_state(task_id, "CANCELED", 60)
