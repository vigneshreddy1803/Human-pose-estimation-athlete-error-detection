# from flask import Flask, render_template, Response, request, redirect, session
# import cv2
# import mediapipe as mp
# import numpy as np
# import joblib
# import os

# app = Flask(__name__)
# app.secret_key = "secret123"

# UPLOAD_FOLDER = "static/uploads"
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# # Load model
# model = joblib.load("pose_model.pkl")

# # MediaPipe
# mp_pose = mp.solutions.pose
# mp_drawing = mp.solutions.drawing_utils
# pose = mp_pose.Pose()

# LABEL_MAP = {
#     0: "Wrong Posture",
#     1: "Correct Posture"
# }

# video_path_global = None   # store uploaded video path


# # ---------------- HOME ----------------
# @app.route("/")
# def home():
#     return render_template("index.html")


# # ---------------- UPLOAD ----------------
# @app.route("/upload", methods=["POST"])
# def upload():
#     global video_path_global

#     file = request.files["video"]
#     path = os.path.join(UPLOAD_FOLDER, file.filename)
#     file.save(path)

#     video_path_global = path

#     return redirect("/")


# # ---------------- STREAM FUNCTION ----------------
# def generate_frames():
#     global video_path_global

#     cap = cv2.VideoCapture(video_path_global)

#     while cap.isOpened():
#         success, frame = cap.read()
#         if not success:
#             break

#         frame = cv2.resize(frame, (800, 600))

#         rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#         results = pose.process(rgb)

#         if results.pose_landmarks:

#             # DRAW SKELETON
#             mp_drawing.draw_landmarks(
#                 frame,
#                 results.pose_landmarks,
#                 mp_pose.POSE_CONNECTIONS
#             )

#             # FEATURE EXTRACTION
#             row = []
#             for lm in results.pose_landmarks.landmark:
#                 row.extend([lm.x, lm.y, lm.z, lm.visibility])

#             row = np.array(row).reshape(1, -1)

#             # PREDICTION
#             prediction = model.predict(row)[0]
#             label = LABEL_MAP[prediction]

#             color = (0,255,0) if prediction == 1 else (0,0,255)

#             cv2.putText(frame, label, (30,50),
#                         cv2.FONT_HERSHEY_SIMPLEX, 1,
#                         color, 3)

#         # Encode frame
#         ret, buffer = cv2.imencode('.jpg', frame)
#         frame = buffer.tobytes()

#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

#     cap.release()


# # ---------------- VIDEO FEED ----------------
# @app.route('/video_feed')
# def video_feed():
#     return Response(generate_frames(),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')


# if __name__ == "__main__":
#     app.run(debug=True)

from flask import Flask, render_template, Response, request, redirect, session, url_for
import cv2
import mediapipe as mp
import numpy as np
import joblib
import os
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load ML model
model = joblib.load("pose_model.pkl")

# MediaPipe setup
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
pose = mp_pose.Pose()

LABEL_MAP = {
    0: "Wrong Posture",
    1: "Correct Posture"
}

video_path_global = None
wrong_events_global = []
stop_stream = False
# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                       (username, password))
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND password=?",
                       (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = username
            return redirect("/index")
        else:
            return "Invalid Credentials ❌"

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")


# ---------------- INDEX ----------------
@app.route("/index")
def index():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html", user=session["user"])


# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["POST"])
def upload():
    global video_path_global

    if "user" not in session:
        return redirect("/login")

    file = request.files["video"]
    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    video_path_global = path

    return redirect("/index")


# ---------------- FRAME GENERATOR ----------------
def generate_frames():
    global video_path_global
    global stop_stream
    global wrong_events_global

    stop_stream = False

    if video_path_global is None:
        return

    cap = cv2.VideoCapture(video_path_global)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 30  # fallback safety

    frame_count = 0
    last_logged_time = -1

    wrong_events_global = []

    while cap.isOpened():

        # STOP CONTROL
        if stop_stream:
            break

        success, frame = cap.read()
        if not success:
            break

        # TIME CALCULATION
        frame_count += 1
        current_time = frame_count / fps

        # RESIZE
        frame = cv2.resize(frame, (800, 600))

        # POSE DETECTION
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:

            # DRAW SKELETON
            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS
            )

            # FEATURE EXTRACTION
            row = []
            for lm in results.pose_landmarks.landmark:
                row.extend([lm.x, lm.y, lm.z, lm.visibility])

            row = np.array(row).reshape(1, -1)

            # PREDICTION
            prediction = model.predict(row)[0]
            label = LABEL_MAP[prediction]

            # LOG WRONG POSTURE
            if prediction == 0:
                if (current_time - last_logged_time) > 1:

                    minutes = int(current_time // 60)
                    seconds = int(current_time % 60)

                    timestamp = f"{minutes:02d}:{seconds:02d}"

                    wrong_events_global.append({
                        "time": timestamp,
                        "issue": "Wrong Running Posture"
                    })

                    last_logged_time = current_time

            # TEXT COLOR
            color = (0,255,0) if prediction == 1 else (0,0,255)

            cv2.putText(frame, label, (30,50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                        color, 3)

        # ENCODE FRAME
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()


# ---------------- VIDEO STREAM ----------------
@app.route('/video_feed')
def video_feed():
    if "user" not in session:
        return redirect("/login")

    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/analysis")
def analysis():
    if "user" not in session:
        return redirect("/login")

    return render_template(
        "result.html",
        video_file=os.path.basename(video_path_global),
        issues=wrong_events_global
    )
    
@app.route("/stop")
def stop():
    global stop_stream
    stop_stream = True
    return "Stopped"

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
    