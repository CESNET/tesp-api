import os
import subprocess
from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from logger_config import logger

app = Flask(__name__)
DATA_DIR = '/data'


@app.route('/upload', defaults={'target_path': ''}, methods=['POST'], strict_slashes=False)
@app.route('/upload/<path:target_path>', methods=['POST'])
def upload_file(target_path):
    if 'file' not in request.files:
        return "No 'file' parameter present in the HTTP request", 400
    file = request.files['file']

    if file.filename == '':
        return 'No selected file', 400

    target_dir = os.path.join(DATA_DIR, target_path)
    os.makedirs(target_dir, exist_ok=True)

    filename = secure_filename(file.filename)
    file.save(os.path.join(target_dir, filename))
    return 'File uploaded successfully.', 200


@app.route('/download/<path:file_path>', methods=['GET'])
def download_file(file_path):
    logger.info(f"path { file_path }")

    target_file = os.path.join(DATA_DIR, file_path)
    if os.path.exists(target_file): 
        return send_file(target_file, as_attachment=True)

    return 'File not found.', 404


@app.route('/list', methods=['GET'])
def list_data():
    try:
        # Run the `ls -la` command on the /data directory
        result = subprocess.run(['ls', '-laR', DATA_DIR], capture_output=True, text=True)

        # Check if the command was successful
        if result.returncode == 0:
            # Split the result into lines
            output = result.stdout.split('\n')
            return jsonify({'status': 'success', 'output': output})
        else:
            return jsonify({'status': 'error', 'message': result.stderr}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
