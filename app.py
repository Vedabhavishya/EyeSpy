from flask import Flask, render_template, Response, request, jsonify, session, redirect, url_for
import cv2
import numpy as np
import os
import time
import threading
import sqlite3
import mediapipe as mp
from ultralytics import YOLO
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

# Database client detection and setup
use_mongodb = False
mongo_client = None
db = None
live_stats = None
sessions = None
users = None
sqlite_db_path = "driver_sessions.db"

try:
    from pymongo import MongoClient
    mongo_client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    mongo_client.admin.command('ping')
    db = mongo_client["driver_monitoring"]
    live_stats = db["driver_live_stats"]
    sessions = db["driver_sessions"]
    users = db["users"]
    use_mongodb = True
    print("Connected to MongoDB successfully.")
except Exception as e:
    print(f"MongoDB connection failed: {e}. Falling back to SQLite.")
    use_mongodb = False

# Initialize SQLite database if MongoDB is not available
if not use_mongodb:
    def init_sqlite():
        conn = sqlite3.connect(sqlite_db_path)
        cursor = conn.cursor()
        
        # Check if users table exists and has username instead of email
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone()
        if table_exists:
            cursor.execute("PRAGMA table_info(users)")
            users_cols = [row[1] for row in cursor.fetchall()]
            if 'username' in users_cols and 'email' not in users_cols:
                print("Migration: dropping old users table to recreate with email primary key.")
                cursor.execute("DROP TABLE users")
                
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash TEXT,
                full_name TEXT,
                phone TEXT,
                age INTEGER
            )
        ''')
        
        # Migrating existing users table if columns are missing
        cursor.execute("PRAGMA table_info(users)")
        users_cols = [row[1] for row in cursor.fetchall()]
        if 'full_name' not in users_cols:
            print("Migration: adding 'full_name' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        if 'phone' not in users_cols:
            print("Migration: adding 'phone' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        if 'age' not in users_cols:
            print("Migration: adding 'age' column to 'users' table.")
            cursor.execute("ALTER TABLE users ADD COLUMN age INTEGER")
        # Create sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_start TEXT,
                session_end TEXT,
                duration_seconds REAL,
                total_blinks INTEGER,
                drowsy_events INTEGER
            )
        ''')
        # Create live_stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                EAR REAL,
                state TEXT,
                blink_rate REAL,
                drowsy INTEGER
            )
        ''')
        
        # SQLite migrations: check if email column exists in sessions and live_stats
        cursor.execute("PRAGMA table_info(sessions)")
        sessions_cols = [row[1] for row in cursor.fetchall()]
        if 'email' not in sessions_cols:
            print("Migration: adding 'email' column to 'sessions' table.")
            cursor.execute("ALTER TABLE sessions ADD COLUMN email TEXT")
            
        cursor.execute("PRAGMA table_info(live_stats)")
        live_stats_cols = [row[1] for row in cursor.fetchall()]
        if 'email' not in live_stats_cols:
            print("Migration: adding 'email' column to 'live_stats' table.")
            cursor.execute("ALTER TABLE live_stats ADD COLUMN email TEXT")
            
        conn.commit()
        conn.close()
    init_sqlite()

app = Flask(__name__)
app.secret_key = "eyespy_secure_session_secret_key_2026"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def db_create_user(email, password_hash):
    if use_mongodb:
        try:
            if users.find_one({"email": email}):
                return False
            users.insert_one({"email": email, "password_hash": password_hash})
            return True
        except Exception as e:
            print(f"Error creating user in MongoDB: {e}")
            return False
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, password_hash))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Error creating user in SQLite: {e}")
            return False

def db_get_user(email):
    if use_mongodb:
        try:
            return users.find_one({"email": email})
        except Exception as e:
            print(f"Error getting user from MongoDB: {e}")
            return None
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            print(f"Error getting user from SQLite: {e}")
            return None

def db_update_profile(email, full_name, phone, age):
    if use_mongodb:
        try:
            users.update_one(
                {"email": email},
                {"$set": {
                    "full_name": full_name,
                    "phone": phone,
                    "age": int(age) if age is not None and age != "" else None
                }}
            )
            return True
        except Exception as e:
            print(f"Error updating user profile in MongoDB: {e}")
            return False
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET full_name = ?, phone = ?, age = ? WHERE email = ?",
                (full_name, phone, int(age) if age is not None and age != "" else None, email)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating user profile in SQLite: {e}")
            return False


MODEL_PATH = r"C:\Users\vedab\runs\detect\train18\weights\best.pt"

if not os.path.exists(MODEL_PATH):
    MODEL_PATH = "yolov8n.pt"

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError("Model file not found.")

model = YOLO(MODEL_PATH)

camera = None

mp_face = mp.solutions.face_mesh
face_mesh = mp_face.FaceMesh(refine_landmarks=True)

LEFT_EYE = [33,160,158,133,153,144]
RIGHT_EYE = [362,385,387,263,373,380]

EAR_THRESHOLD = 0.21
DROWSY_FRAMES = 20
BLINK_HIGH_RATE = 25

alert_active = False

session_start = None
total_blinks = 0
drowsy_events = 0
last_db_write = 0

# Real-time telemetry memory store for API polling
current_telemetry = {
    "ear": 0.0,
    "state": "OPEN",
    "blink_rate": 0.0,
    "total_blinks": 0,
    "drowsy": False,
    "drowsy_events": 0,
    "active_seconds": 0
}

def save_live_data(ear, state, blink_rate, drowsy, email):
    timestamp_str = datetime.now().isoformat()
    if use_mongodb:
        try:
            live_stats.insert_one({
                "email": email,
                "timestamp": datetime.now(),
                "EAR": float(ear),
                "state": state,
                "blink_rate": float(blink_rate),
                "drowsy": bool(drowsy)
            })
        except Exception as e:
            print(f"Error saving to MongoDB: {e}")
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO live_stats (timestamp, EAR, state, blink_rate, drowsy, email) VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp_str, float(ear), state, float(blink_rate), int(drowsy), email)
            )
            # Limit table size to keep it fast per user
            cursor.execute("DELETE FROM live_stats WHERE email = ? AND id NOT IN (SELECT id FROM live_stats WHERE email = ? ORDER BY id DESC LIMIT 100)", (email, email))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving to SQLite: {e}")

def save_session(start_time, end_time, duration, blinks, drowsy_evs, email):
    if use_mongodb:
        try:
            sessions.insert_one({
                "email": email,
                "session_start": start_time,
                "session_end": end_time,
                "duration_seconds": float(duration),
                "total_blinks": int(blinks),
                "drowsy_events": int(drowsy_evs)
            })
        except Exception as e:
            print(f"Error saving session to MongoDB: {e}")
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (session_start, session_end, duration_seconds, total_blinks, drowsy_events, email) VALUES (?, ?, ?, ?, ?, ?)",
                (start_time.isoformat() if hasattr(start_time, 'isoformat') else str(start_time),
                 end_time.isoformat() if hasattr(end_time, 'isoformat') else str(end_time),
                 float(duration), int(blinks), int(drowsy_evs), email)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving session to SQLite: {e}")

def get_sessions(email):
    if use_mongodb:
        try:
            docs = list(sessions.find({"email": email}).sort("session_start", -1))
            for doc in docs:
                doc['_id'] = str(doc['_id'])
                if isinstance(doc.get('session_start'), datetime):
                    doc['session_start'] = doc['session_start'].isoformat()
                if isinstance(doc.get('session_end'), datetime):
                    doc['session_end'] = doc['session_end'].isoformat()
            return docs
        except Exception as e:
            print(f"Error fetching from MongoDB: {e}")
            return []
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE email = ? ORDER BY id DESC", (email,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error fetching from SQLite: {e}")
            return []

def clear_sessions_db(email):
    if use_mongodb:
        try:
            sessions.delete_many({"email": email})
            live_stats.delete_many({"email": email})
            return True
        except Exception as e:
            print(f"Error clearing MongoDB: {e}")
            return False
    else:
        try:
            conn = sqlite3.connect(sqlite_db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE email = ?", (email,))
            cursor.execute("DELETE FROM live_stats WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error clearing SQLite: {e}")
            return False


def play_alert():
    threading.Thread(
        target=playsound,
        args=("alert.wav",),
        daemon=True
    ).start()


def ear_calc(landmarks, eye_idx, w, h):

    pts = [(int(landmarks[i].x*w), int(landmarks[i].y*h)) for i in eye_idx]

    v1 = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    v2 = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    h_dist = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))

    return (v1 + v2) / (2.0 * h_dist)



@app.route("/login")
def login():
    if 'email' in session:
        return redirect(url_for('home'))
    return render_template("login.html")

@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    import re
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400
        
    EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(EMAIL_REGEX, email):
        return jsonify({"success": False, "message": "Invalid email address format."}), 400
        
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters long."}), 400
        
    hashed = generate_password_hash(password)
    
    if db_create_user(email, hashed):
        session.permanent = True
        session["email"] = email
        return jsonify({"success": True, "message": "Registration successful."})
    else:
        return jsonify({"success": False, "message": "Email already exists."}), 400

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required."}), 400
        
    user = db_get_user(email)
    if user and check_password_hash(user["password_hash"], password):
        session.permanent = True
        session["email"] = email
        return jsonify({"success": True, "message": "Login successful."})
    else:
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

@app.route("/logout")
def logout():
    global camera
    global session_start
    global total_blinks
    global drowsy_events

    if camera:
        try:
            camera.release()
        except Exception as e:
            print(f"Error releasing camera on logout: {e}")
        camera = None

    if session_start:
        email = session.get('email')
        end_time = datetime.now()
        duration_seconds = (end_time - session_start).total_seconds()
        save_session(session_start, end_time, duration_seconds, total_blinks, drowsy_events, email)
        session_start = None

    session.clear()
    return redirect(url_for('login'))

@app.route("/api/profile")
@login_required
def api_get_profile():
    email = session.get('email')
    user = db_get_user(email)
    if not user:
        return jsonify({"success": False, "message": "User not found."}), 404
        
    return jsonify({
        "success": True,
        "profile": {
            "email": user.get("email"),
            "full_name": user.get("full_name") or "",
            "phone": user.get("phone") or "",
            "age": user.get("age") or ""
        }
    })

@app.route("/api/profile/update", methods=["POST"])
@login_required
def api_update_profile():
    data = request.get_json() or {}
    full_name = data.get("full_name", "").strip()
    phone = data.get("phone", "").strip()
    age = data.get("age")
    
    if age is not None and age != "":
        try:
            age_int = int(age)
            if age_int < 1 or age_int > 120:
                return jsonify({"success": False, "message": "Age must be between 1 and 120."}), 400
        except ValueError:
            return jsonify({"success": False, "message": "Age must be a valid number."}), 400

    email = session.get('email')
    if db_update_profile(email, full_name, phone, age):
        return jsonify({"success": True, "message": "Profile updated successfully."})
    else:
        return jsonify({"success": False, "message": "Failed to update profile."}), 500

@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/image-analysis")
@login_required
def image_analysis():
    return render_template("image_analysis.html")

@app.route("/live-stream")
@login_required
def live_stream():
    return render_template("live_stream.html")

@app.route("/driving-mode")
@login_required
def driving_mode():
    global session_start
    global total_blinks
    global drowsy_events

    session_start = datetime.now()
    total_blinks = 0
    drowsy_events = 0

    return render_template("driving_mode.html")

driver_states = {}

def get_driver_state(email):
    if email not in driver_states:
        driver_states[email] = {
            "session_start": None,
            "total_blinks": 0,
            "drowsy_events": 0,
            "blink_count": 0,
            "blink_start_time": None,
            "eye_closed_start_time": None,
            "prev_state": "OPEN",
            "prev_ear": 0.0,
            "calibrated": False,
            "calibration_count": 0,
            "calibration_ears": [],
            "calibrated_threshold": EAR_THRESHOLD,
            "alert_active": False,
            "last_db_write": 0.0,
            "current_telemetry": {
                "ear": 0.0,
                "state": "OPEN",
                "blink_rate": 0.0,
                "total_blinks": 0,
                "drowsy": False,
                "drowsy_events": 0,
                "active_seconds": 0
            }
        }
    return driver_states[email]

@app.route('/api/start-session', methods=['POST'])
@login_required
def api_start_session():
    email = session.get('email')
    if email in driver_states:
        del driver_states[email]
    
    state = get_driver_state(email)
    state["session_start"] = datetime.now()
    state["blink_start_time"] = time.time()
    state["eye_closed_start_time"] = time.time()
    state["last_db_write"] = time.time()
    return jsonify({"success": True, "message": "Session started."})

@app.route('/api/stop-session', methods=['POST'])
@login_required
def api_stop_session():
    email = session.get('email')
    state = get_driver_state(email)
    if state["session_start"]:
        end_time = datetime.now()
        duration_seconds = (end_time - state["session_start"]).total_seconds()
        save_session(state["session_start"], end_time, duration_seconds, state["total_blinks"], state["drowsy_events"], email)
        state["session_start"] = None
    if email in driver_states:
        del driver_states[email]
    return jsonify({"success": True, "message": "Session stopped and saved."})

@app.route('/api/process-frame', methods=['POST'])
@login_required
def api_process_frame():
    import base64
    email = session.get('email')
    state = get_driver_state(email)
    
    data = request.get_json() or {}
    image_data = data.get("image", "")
    mode = data.get("mode", "live")
    
    if not image_data:
        return jsonify({"success": False, "message": "No image data"}), 400
        
    header, encoded = image_data.split(",", 1)
    img_bytes = base64.b64decode(encoded)
    npimg = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    
    if frame is None:
        return jsonify({"success": False, "message": "Invalid image"}), 400

    results = model(frame, conf=0.3)
    boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []
    
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)
    
    state_str = "OPEN"
    ear_val = 0.0
    left_ear_val = 0.0
    right_ear_val = 0.0
    head_tilt = 0.0
    drowsy = False
    
    if res.multi_face_landmarks:
        h, w, _ = frame.shape
        lm = res.multi_face_landmarks[0].landmark
        left_ear_val = ear_calc(lm, LEFT_EYE, w, h)
        right_ear_val = ear_calc(lm, RIGHT_EYE, w, h)
        ear_raw = (left_ear_val + right_ear_val) / 2
        
        ear_val = 0.7 * state["prev_ear"] + 0.3 * ear_raw
        state["prev_ear"] = ear_val
        
        dx = lm[152].x - lm[10].x
        dy = lm[152].y - lm[10].y
        head_tilt = round(np.degrees(np.arctan2(dx, dy)), 2)
        
        if mode == "driving":
            if not state["calibrated"]:
                state["calibration_ears"].append(ear_raw)
                state["calibration_count"] += 1
                if state["calibration_count"] >= 50:
                    avg_open_ear = sum(state["calibration_ears"]) / len(state["calibration_ears"])
                    state["calibrated_threshold"] = round(avg_open_ear * 0.75, 3)
                    state["calibrated"] = True
                    state["blink_start_time"] = time.time()
                    state["eye_closed_start_time"] = time.time()
                
                cv2.putText(frame, f"CALIBRATING EYE MESH ({state['calibration_count']}/50)",
                            (20,40), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0,255,255), 2)
                cv2.putText(frame, "KEEP EYES OPEN & LOOK AHEAD",
                            (20,70), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0,255,255), 2)
            else:
                if ear_val < state["calibrated_threshold"]:
                    if state["prev_state"] == "OPEN":
                        state["eye_closed_start_time"] = time.time()
                    state_str = "CLOSED"
                    closed_duration = time.time() - state["eye_closed_start_time"]
                else:
                    if state["prev_state"] == "CLOSED":
                        closed_duration = time.time() - state["eye_closed_start_time"]
                        if 0.05 <= closed_duration <= 0.55:
                            state["blink_count"] += 1
                            state["total_blinks"] += 1
                    state_str = "OPEN"
                    closed_duration = 0.0
                    
                state["prev_state"] = state_str
                
                if state["blink_start_time"] is None:
                    state["blink_start_time"] = time.time()
                elapsed_time = time.time() - state["blink_start_time"]
                blink_rate = 0.0
                if elapsed_time > 10:
                    blink_rate = (state["blink_count"] / elapsed_time) * 60
                if elapsed_time > 60:
                    state["blink_count"] = 0
                    state["blink_start_time"] = time.time()
                    
                drowsy = (closed_duration > 1.0) or (blink_rate > BLINK_HIGH_RATE)
                
                if drowsy:
                    if not state["alert_active"]:
                        state["alert_active"] = True
                        state["drowsy_events"] += 1
                else:
                    state["alert_active"] = False
                    
                state["current_telemetry"] = {
                    "ear": round(float(ear_val), 4),
                    "state": state_str,
                    "blink_rate": round(float(blink_rate), 2),
                    "total_blinks": int(state["total_blinks"]),
                    "drowsy": bool(drowsy),
                    "drowsy_events": int(state["drowsy_events"]),
                    "active_seconds": int((datetime.now() - state["session_start"]).total_seconds()) if state["session_start"] else 0
                }
                
                if time.time() - state["last_db_write"] > 1:
                    save_live_data(ear_val, state_str, blink_rate, drowsy, email)
                    state["last_db_write"] = time.time()
        else:
            state_str = "CLOSED" if ear_val < EAR_THRESHOLD else "OPEN"
    else:
        state_str = "OFFLINE"

    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        color = (0, 255, 0) if state_str == "OPEN" else (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, state_str, (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.6, color, 2)

    _, buffer = cv2.imencode('.jpg', frame)
    encoded_img = base64.b64encode(buffer).decode('utf-8')
    
    response_data = {
        "success": True,
        "image": f"data:image/jpeg;base64,{encoded_img}",
        "ear": round(float(ear_val), 3),
        "left_ear": round(float(left_ear_val), 3),
        "right_ear": round(float(right_ear_val), 3),
        "state": state_str,
        "head_tilt": head_tilt,
        "eyes_found": len(boxes),
        "drowsy": drowsy
    }
    
    if mode == "driving":
        response_data.update(state["current_telemetry"])
        
    return jsonify(response_data)




@app.route('/detect-image', methods=['POST'])
@login_required
def detect_image():
    import base64

    file = request.files['image']
    img_bytes = file.read()

    npimg = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # 1. YOLO eye detection
    results = model(frame, conf=0.3)
    boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []

    # 2. MediaPipe Face Mesh for EAR and Posture
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)

    ear_val = 0.0
    left_ear_val = 0.0
    right_ear_val = 0.0
    state_str = "OFFLINE"
    head_tilt = 0.0

    if res.multi_face_landmarks:
        h, w, _ = frame.shape
        lm = res.multi_face_landmarks[0].landmark
        left_ear_val = ear_calc(lm, LEFT_EYE, w, h)
        right_ear_val = ear_calc(lm, RIGHT_EYE, w, h)
        ear_val = (left_ear_val + right_ear_val) / 2
        state_str = "CLOSED" if ear_val < EAR_THRESHOLD else "OPEN"

        # Calculate head tilt (nose to chin and forehead tilt)
        dx = lm[152].x - lm[10].x
        dy = lm[152].y - lm[10].y
        head_tilt = round(np.degrees(np.arctan2(dx, dy)), 2)

    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        color = (0, 255, 0) if state_str == "OPEN" else (0, 0, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, state_str, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, color, 2)

    _, buffer = cv2.imencode('.jpg', frame)
    encoded_img = base64.b64encode(buffer).decode('utf-8')

    return jsonify({
        "image": f"data:image/jpeg;base64,{encoded_img}",
        "ear": round(float(ear_val), 3),
        "left_ear": round(float(left_ear_val), 3),
        "right_ear": round(float(right_ear_val), 3),
        "state": state_str,
        "head_tilt": head_tilt,
        "eyes_found": len(boxes)
    })

@app.route('/detect-live')
@login_required
def detect_live():
    return "Streaming is now client-side."


@app.route('/detect-drowsy')
@login_required
def detect_drowsy():
    return "Streaming is now client-side."


@app.route('/stop-live')
@login_required
def stop_live():
    # Deprecated: client calls /api/stop-session now
    return "Stopped"


@app.route('/api/live-stats')
@login_required
def api_live_stats():
    email = session.get('email')
    state = get_driver_state(email)
    return jsonify(state["current_telemetry"])


@app.route('/api/history')
@login_required
def api_history():
    email = session.get('email')
    return jsonify(get_sessions(email))


@app.route('/api/history/clear', methods=['POST'])
@login_required
def api_clear_history():
    email = session.get('email')
    success = clear_sessions_db(email)
    return jsonify({"success": success})


if __name__ == "__main__":
    app.run(debug=False, threaded=True)