from flask import Flask, render_template, Response, request
import cv2
import numpy as np
from ultralytics import YOLO

app = Flask(__name__)

# Load YOLO model
model = YOLO(r"C:\Users\vedab\runs\detect\train18\weights\best.pt")

# GLOBAL CAMERA VARIABLE
camera = None


@app.route("/")
def home():
    return render_template("index.html")


# ---------------- IMAGE DETECTION ----------------
@app.route('/detect-image', methods=['POST'])
def detect_image():
    file = request.files['image']
    img_bytes = file.read()
    npimg = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    results = model(frame, conf=0.30)
    annotated = results[0].plot()

    _, buffer = cv2.imencode('.jpg', annotated)
    return Response(buffer.tobytes(), mimetype='image/jpeg')


# ---------------- LIVE WEBCAM STREAM ----------------
def generate_frames():
    global camera

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
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               frame_bytes + b'\r\n')

    if camera:
        camera.release()
        camera = None


@app.route('/detect-live')
def detect_live():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# ---------------- STOP WEBCAM ----------------
@app.route('/stop-live')
def stop_live():
    global camera
    if camera:
        camera.release()
        camera = None
        cv2.destroyAllWindows()
    return "Camera Stopped"


if __name__ == "__main__":
    app.run(debug=True)