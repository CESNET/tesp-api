
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

def _wait_for_state(id, expected_state, timeout = 10):
    for i in range(timeout):
        resp = _get_request(f"/v1/tasks/{id}")
        actual_state = _gnv(resp, "state")
        
        # end on right state
        if actual_state == expected_state:
            return resp
        
        # raise exception on wrong state (not right state and not RUNNING state)
        if actual_state != "INITIALIZING" and actual_state != "QUEUED" and actual_state != "RUNNING":
            raise Exception(f"_wait_for_state(): unexpected state. ID: {id}, expected: {expected_state}, given: {actual_state}")
        
        time.sleep(1)
        
    raise Exception(f"_wait_for_state(): timeout. ID: {id}, state: {actual_state}")

def _test_simple(json, timeout, expected_state = 'COMPLETE'):
    # submit task
    json = _open_json(json)
    resp = _post_request("/v1/tasks", payload=json).json()

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    return _wait_for_state(id, expected_state, timeout)

def _test_activity(json, timeout_running, timeout_complete, expected_state = 'COMPLETE'):
    # submit task
    json = _open_json(json)
    resp = _post_request("/v1/tasks", payload=json).json()

    # get ID of the already started task
    id = _gnv(resp, "id")

    # try to get status of the task
    if not _wait_for_state(id, 'RUNNING', timeout_running):
        return False
    return _wait_for_state(id, expected_state, timeout_complete)

    task_response = _wait_for_state(id, expected_state, timeout_complete)

    # Retrieve and print resources if they exist
    resources = _gnv(task_response, "resources")
    if resources:
        print(f"Resources for task {id}: {resources}")
    else:
        print(f"No resources found for task {id}.")

    return task_response

def _test_sequence_simple(jsons, timeout, expected_state = 'COMPLETE'):
    for file_name in jsons:
        json = f'{file_name}.json'
        if not _test_simple(json, timeout, expecetd_state):
            return False

    return True

def _test_sequence_activity(jsons, timeout_running, timeout_complete, expected_state = 'COMPLETE'):
    for file_name in jsons:
        json = f'{file_name}.json'
        if not _test_activity(json, timeout_running, timeout_complete, expected_state):
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

# Submits task with expected state: COMPLETE.
def test_submit_task_complete():
    assert _test_activity("state_true.json", 10, 60, 'COMPLETE')

# Submits task with expected state: EXECUTOR_ERROR.
def test_submit_task_fail():
    assert _test_activity("state_false.json", 10, 60, 'EXECUTOR_ERROR')

# Submits multiple tasks with expected state: COMPLETE.
def test_submit_task_multi_complete():
    assert _test_activity("multi_true.json", 10, 60, 'COMPLETE')

# Submits multiple tasks with expected state: EXECUTOR_ERROR.
def test_submit_task_multi_fail():
    jsons = ["multi_false_1", "multi_false_2", "multi_false_3"]
    assert _test_sequence_activity(jsons, 10, 60, 'EXECUTOR_ERROR')

# Lists tasks.
def test_get_task_list():
    data = _get_request("/v1/tasks")

    tasks = _gnv(data, "tasks")
    assert tasks
    assert isinstance(tasks, list)

# Tests only HTTP download for now and direct input.
def test_inputs():
    assert _test_simple("inputs.json", 120)

#def test_outputs():
    # Tests S3 and FTP upload and download.
    #jsons = ["outputs-prepare", "outputs-prepare-check", "outputs-test", "outputs-test-check"]
    #assert _test_sequence_simple(jsons, 180)

# Downloads and copies file to the shared volume and displays its content with two separate executors.
def test_volumes():
    assert _test_simple("volumes.json", 100)

# Verifies that environment variables from envs.json are correctly echoed to output files with expected content. 
def test_envs():
    assert _test_simple("envs.json", 100)
    
    expected_files = {
        f"{script_directory}/test_data/env_test_1": "first upload successful\n",
        f"{script_directory}/test_data/env_test_2": "second upload successful\n"
    }
    
    # Verify that each file was created with the expected content
    for path, expected_content in expected_files.items():
        # Open the file and read its content (if accessible in the current environment)
        with open(path, 'r') as f:
            content = f.read()
        assert content == expected_content, f"File {path} does not contain the expected content."

# Displays CPU information by reading /proc/cpuinfo in different ways, prints the working directory by running pwd from /bin.
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

# Cancels a concrete task in RUNNING state.
def test_task_cancel():
    response = _test_simple("cancel.json", 60, "RUNNING")
    task_id = _gnv(response, "id")
    assert task_id
    _post_request(f"/v1/tasks/{task_id}:cancel")
    assert _wait_for_state(task_id, "CANCELED", 60)

# Checks whether given task exceeds available resources.
def test_resource_check_with_limits():
    # Load the JSON file
    json_data = _open_json('resource_check.json')

    # Extract CPU cores and RAM values
    cpu_cores = _gnv(json_data, "resources.cpu_cores")
    ram_gb = _gnv(json_data, "resources.ram_gb")

    # Define the maximum limits
    max_cpu_cores = 4
    max_ram_gb = 3.8

    # Perform the checks with limits
    assert cpu_cores <= max_cpu_cores, f"CPU cores exceed the limit: {cpu_cores} > {max_cpu_cores}"
    assert ram_gb <= max_ram_gb, f"RAM exceeds the limit: {ram_gb} > {max_ram_gb}"

    print(f"Requested resources: CPU cores = {cpu_cores}, RAM = {ram_gb} GB (Limits: {max_cpu_cores} cores, {max_ram_gb} GB RAM)")

