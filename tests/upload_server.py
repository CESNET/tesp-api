import os
import sys
from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename

HOME_DIR = sys.path[0]  # resolves to /home/debian
UPLOAD_ROOT = os.path.join(HOME_DIR, "uploaded_data")
SERVE_ROOT = HOME_DIR

app = Flask(__name__)

# Handle file upload
@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    uploaded_file = request.files['file']
    raw_filename = uploaded_file.filename  # may include subdir e.g. "subdir/file.txt"

    # Secure each path part
    secure_parts = [secure_filename(part) for part in raw_filename.split('/') if part]
    safe_path = os.path.join(UPLOAD_ROOT, *secure_parts)

    # Ensure parent dir exists
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    uploaded_file.save(safe_path)

    return jsonify({"status": "ok", "saved_as": safe_path})

@app.route('/<path:subpath>', methods=['GET'])
@app.route('/<path:subpath>/', methods=['GET'])
def browse(subpath):
    full_path = os.path.join(SERVE_ROOT, subpath)

    if os.path.isdir(full_path):
        # Directory listing
        items = os.listdir(full_path)
        links = []
        for item in items:
            item_path = os.path.join(subpath, item)
            if os.path.isdir(os.path.join(full_path, item)):
                item_path += '/'
            links.append(f"<a href='/{item_path}'>{item}</a><br>")
        return "<html><body>" + "\n".join(links) + "</body></html>"

    elif os.path.isfile(full_path):
        # Serve file
        return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))

    else:
        abort(404, description=f"{subpath} not found")

if __name__ == '__main__':
    os.makedirs(UPLOAD_ROOT, exist_ok=True)
    print(f"Uploading to: {UPLOAD_ROOT}")
    print(f"Serving from: {SERVE_ROOT}")
    app.run(host='0.0.0.0', port=5000, debug=True)

