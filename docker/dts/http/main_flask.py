from flask import Flask, request, send_file, send_from_directory
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400

    file = request.files['file']

    if file.filename == '':
        return 'No selected file', 400

    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join('/data', filename))
        return 'File uploaded successfully.', 200
    return 'No file received.', 400

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory('/data', filename, as_attachment=True)
    file_path = os.path.join('uploads', filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return 'File not found.', 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

