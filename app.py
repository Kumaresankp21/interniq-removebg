from flask import Flask, request, send_file, jsonify, render_template
from rembg import remove
from PIL import Image
import io
import base64
import uuid
import os
import tempfile
import time

app = Flask(__name__)

# Directory to store images temporarily
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Expiry time in seconds (e.g., 300 seconds = 5 minutes)
FILE_EXPIRY_TIME = 300

# Dictionary to track file creation times
file_creation_times = {}

def create_temp_file(content, prefix, suffix):
    """Create a temporary file with the given content and return the file path."""
    temp_file = tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, dir=UPLOAD_FOLDER, delete=False)
    temp_file.write(content)
    temp_file.close()
    return temp_file.name

def cleanup_files():
    """Delete expired files."""
    current_time = time.time()
    for file_path, creation_time in list(file_creation_times.items()):
        if current_time - creation_time > FILE_EXPIRY_TIME:
            if os.path.exists(file_path):
                os.remove(file_path)
                del file_creation_times[file_path]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/remove-background', methods=['POST'])
def remove_background():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        # Open the uploaded image
        image = Image.open(file.stream)

        # Create unique IDs for the images
        file_id = str(uuid.uuid4())

        # Process image to remove background
        output = remove(image)

        # Save original image to a temporary file
        original_byte_arr = io.BytesIO()
        image.save(original_byte_arr, format='PNG')
        original_file_path = create_temp_file(original_byte_arr.getvalue(), prefix=f'interniq_{file_id}_', suffix='.png')

        # Save processed image to a temporary file
        processed_byte_arr = io.BytesIO()
        output.save(processed_byte_arr, format='PNG')
        processed_file_path = create_temp_file(processed_byte_arr.getvalue(), prefix=f'interniq_{file_id}_', suffix='.png')

        # Track file creation times
        file_creation_times[original_file_path] = time.time()
        file_creation_times[processed_file_path] = time.time()

        # Encode images to base64
        with open(original_file_path, 'rb') as f:
            original_image_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        with open(processed_file_path, 'rb') as f:
            processed_image_base64 = base64.b64encode(f.read()).decode('utf-8')

        # Return a JSON response with both images and file IDs
        return jsonify({
            "file_id": file_id,
            "original_image": f"data:image/png;base64,{original_image_base64}",
            "processed_image": f"data:image/png;base64,{processed_image_base64}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<file_id>/<image_type>')
def download_image(file_id, image_type):
    if image_type not in ['original', 'processed']:
        return jsonify({"error": "Invalid image type"}), 400

    # Find files that match the given file_id and image_type
    temp_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.startswith(f'interniq_{file_id}_') and f.endswith('.png')]
    
    if not temp_files:
        return jsonify({"error": "File not found"}), 404

    # Assuming there will be only one matching file
    file_path = os.path.join(UPLOAD_FOLDER, temp_files[0])

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    response = send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))

    # Clean up the file after sending
    cleanup_files()

    return response

if __name__ == '__main__':
    # Clean up expired files periodically
    import threading
    def periodic_cleanup():
        while True:
            cleanup_files()
            time.sleep(FILE_EXPIRY_TIME)

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()

    app.run(debug=True)
