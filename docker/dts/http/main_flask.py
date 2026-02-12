import os
import subprocess
from flask import Flask, request, send_file, send_from_directory, jsonify, abort
from werkzeug.utils import secure_filename
from logger_config import logger

app = Flask(__name__)
DATA_DIR = '/data'
UPLOAD_DIR = '/data/uploaded_data'


@app.route('/upload', defaults={'target_path': ''}, methods=['POST'], strict_slashes=False)
@app.route('/upload/<path:target_path>', methods=['POST'])
def upload_file(target_path):
    if 'file' not in request.files:
        return "No 'file' parameter present in the HTTP request", 400
    file = request.files['file']

    if file.filename == '':
        return 'No selected file', 400

    # Support nested paths in filename (e.g., "subdir/file.txt")
    raw_filename = file.filename
    secure_parts = [secure_filename(part) for part in raw_filename.split('/') if part]
    
    if target_path:
        target_dir = os.path.join(UPLOAD_DIR, target_path)
    else:
        target_dir = UPLOAD_DIR
        
    if len(secure_parts) > 1:
        target_dir = os.path.join(target_dir, *secure_parts[:-1])
        
    os.makedirs(target_dir, exist_ok=True)
    filename = secure_parts[-1] if secure_parts else secure_filename(raw_filename)
    save_path = os.path.join(target_dir, filename)
    file.save(save_path)
    
    return jsonify({"status": "ok", "saved_as": save_path}), 200


@app.route('/download/<path:file_path>', methods=['GET'])
def download_file(file_path):
    """Legacy download route for backwards compatibility."""
    logger.info(f"path { file_path }")

    target_file = os.path.join(DATA_DIR, file_path)
    if os.path.exists(target_file): 
        return send_file(target_file, as_attachment=True)

    return 'File not found.', 404


@app.route('/test_data/', methods=['GET'])
@app.route('/test_data/<path:subpath>', methods=['GET'])
def browse_test_data(subpath=''):
    """Serve files and directory listings from /data (mounted as test_data)."""
    full_path = os.path.join(DATA_DIR, subpath)
    
    if os.path.isdir(full_path):
        # Directory listing
        items = os.listdir(full_path)
        links = []
        for item in items:
            item_path = os.path.join('test_data', subpath, item) if subpath else os.path.join('test_data', item)
            if os.path.isdir(os.path.join(full_path, item)):
                item_path += '/'
            links.append(f"<a href='/{item_path}'>{item}</a><br>")
        return "<html><body>" + "\n".join(links) + "</body></html>"
    
    elif os.path.isfile(full_path):
        # Serve file
        return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
    
    else:
        abort(404, description=f"{subpath} not found")


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
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    app.run(host='0.0.0.0', debug=True, port=5000)

