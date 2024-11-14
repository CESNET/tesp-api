import pytest
import requests
import time
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

base_url = "http://localhost:8080"
script_directory = os.path.dirname(os.path.abspath(__file__))

# Helper functions
def _post_request(url, payload={}):
    """Send a POST HTTP request, test the status, jsonization and return the response in JSON."""
    resp = requests.post(f"{base_url}{url}", json=payload)
    assert resp.status_code == 200
    assert resp.json()
    return resp.json()

def _get_request(url):
    """Send a GET HTTP request, test the status, jsonization and return the response in JSON."""
    resp = requests.get(f"{base_url}{url}")
    assert resp.status_code == 200
    assert resp.json()
    return resp.json()

def _wait_for_state(task_id, target_state, timeout=100):
    """Wait for a task to reach the desired state (e.g., COMPLETE, CANCELED) or timeout."""
    for _ in range(timeout):
        resp = _get_request(f"/v1/tasks/{task_id}")
        state = resp.get("state")
        if state == target_state:
            return resp
        time.sleep(1)
    raise Exception(f"Task {task_id} did not reach state {target_state} within {timeout} seconds")

def _open_json(filename):
    """Open a JSON file from the test_jsons directory."""
    with open(f"{script_directory}/test_jsons/{filename}", 'r') as f:
        data = f.read()
    return json.loads(data)


# Test function to stress test by submitting multiple tasks using JSON files
def test_stress_multiple_task_submission():
    task_filename = "load_stress.json"  # JSON file defining the task
    task_payload = _open_json(task_filename)
    
    num_tasks = 100  # Number of tasks to submit
    submitted_tasks = []

    # Submit tasks concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_post_request, "/v1/tasks", task_payload) for _ in range(num_tasks)]
        
        # Collect the submitted task IDs
        for future in as_completed(futures):
            try:
                response = future.result()
                task_id = response.get("id")
                assert task_id, "No task ID found in response"
                submitted_tasks.append(task_id)
            except Exception as e:
                pytest.fail(f"Task submission failed: {e}")

    # Ensure all tasks were submitted successfully
    assert len(submitted_tasks) == num_tasks, f"Only {len(submitted_tasks)} out of {num_tasks} tasks were submitted"

    # Check if all tasks eventually complete
    completed_tasks = 0
    for task_id in submitted_tasks:
        try:
            _wait_for_state(task_id, "COMPLETE", timeout=100)  # Wait for each task to complete
            completed_tasks += 1
        except Exception as e:
            print(f"Task {task_id} failed to complete: {e}")

    # Ensure that all tasks completed successfully
    assert completed_tasks == num_tasks, f"Only {completed_tasks} out of {num_tasks} tasks completed"

if __name__ == "__main__":
    pytest.main()

