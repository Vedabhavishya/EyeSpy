from flask import Flask, render_template, Response, request, jsonify
import cv2
import numpy as np
import os

app = Flask(__name__)

# Try to load YOLO but handle failure gracefully for environment without it
ULTRALYTICS_AVAILABLE = False
model = None
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
    # Placeholder for model path - user should upload their best.pt to models/
    MODEL_PATH = "models/best.pt"
    if os.path.exists(MODEL_PATH):
        model = YOLO(MODEL_PATH)
    else:
        # Fallback to a default model if possible, or stay None
        try:
            model = YOLO("yolov8n.pt")
        except:
            model = None
except ImportError:
    pass

# GLOBAL CAMERA VARIABLE
camera = None

@app.route("/")
def home():
    return render_template("index.html")

@app.route('/detect-image', methods=['POST'])
def detect_image():
    if not ULTRALYTICS_AVAILABLE or model is None:
        return "Detection model not loaded. Please ensure ultralytics is installed and model is present.", 503
    
    if 'image' not in request.files:
        return "No image uploaded", 400
    file = request.files['image']
    img_bytes = file.read()
    npimg = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    results = model(frame, conf=0.30)
    annotated = results[0].plot()

    _, buffer = cv2.imencode('.jpg', annotated)
    return Response(buffer.tobytes(), mimetype='image/jpeg')

def generate_frames():
    global camera
    if not ULTRALYTICS_AVAILABLE or model is None:
        return

    camera = cv2.VideoCapture(0)
    while True:
        if camera is None:
            break
        success, frame = camera.read()
        if not success:
            break

        results = model(frame, conf=0.30)
        annotated = results[0].plot()
        _, buffer = cv2.imencode('.jpg', annotated)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/detect-live')
def detect_live():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stop-live')
def stop_live():
    global camera
    if camera:
        camera.release()
        camera = None
    return "Camera Stopped"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
