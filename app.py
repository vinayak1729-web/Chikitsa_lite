from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from flask_socketio import SocketIO, emit
from flask_mail import Mail, Message
import json
import os
from pathlib import Path
import bcrypt
from dotenv import load_dotenv
import requests
import csv
import pandas as pd
from datetime import datetime, timedelta, date
from functools import wraps
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import secrets
import hashlib
import base64
import statistics
from werkzeug.utils import secure_filename
import logging

# Placeholder for custom modules (implement these as needed)
def get_random_close_questions():
    return [{"id": 1, "text": "Do you feel stressed?", "options": ["Yes", "No"]}]
def get_random_open_questions():
    return [{"id": 1, "text": "Describe your current mood."}]
def csv_to_string(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""
def chatbot_response(message):
    return "Placeholder response"
def analyze_image(image_path):
    return "Placeholder image analysis"
def Gemini_prompt_main():
    return "Main prompt for Gemma"
def Gemini_Questionaire_prompt():
    return "Questionnaire prompt for Gemma"
def image_prompt():
    return "Image analysis prompt for Gemma"

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'instance/uploads'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS')

# Initialize Flask-Mail and SocketIO
mail = Mail(app)
socketio = SocketIO(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ollama API configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
SYSTEM_PROMPT = """
You are Chikitsa, an empathetic AI psychiatrist, providing mental health support using evidence-based coping strategies, behaving like a best friend, showing love, care, and secular Bhagavad Gita lessons (e.g., focus on the present, detachment from outcomes) tailored to users' emotional needs. Acknowledge feelings, assess concerns, suggest actionable techniques, and recommend professional help for severe symptoms. Use a warm, inclusive tone, avoid religious references, and encourage gradual progress. Format your responses in markdown for clear presentation.
Reply like a real human, in 1 line only like a real human, show emotions and all; if user is male act like female, if female then act like male.
"""

# File paths
USERS_FILE = Path("instance/users.json")
RATINGS_FILE = Path("instance/rating/ratings.json")
BASE_DIRS = {
    "game_userdata": "instance/game/user_data",
    "game_video": "instance/game/video",
    "game_audio": "instance/game/audio"
}

# Ensure directories exist
def ensure_directories():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('instance/appointments', exist_ok=True)
    os.makedirs('instance/mood_data', exist_ok=True)
    os.makedirs('instance/meditation_data', exist_ok=True)
    os.makedirs('instance/user_data', exist_ok=True)
    os.makedirs('responses/close_ended', exist_ok=True)
    os.makedirs('responses/open_ended', exist_ok=True)
    for dir_path in BASE_DIRS.values():
        os.makedirs(dir_path, exist_ok=True)

# File handling utilities
def load_json_file(file_path):
    try:
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return []

def save_json_file(file_path, data):
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

# User management
def load_users():
    return load_json_file(USERS_FILE)

def save_users(users):
    return save_json_file(USERS_FILE, users)

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("Please log in to access this page", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not all([name, email, password]):
            flash("All fields are required", "error")
            return render_template('register.html')

        users = load_users()
        if any(user['email'] == email or user['name'] == name for user in users):
            flash("Email or username already exists", "error")
            return render_template('register.html')

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        new_user = {
            'name': name,
            'email': email,
            'password': hashed_password,
            'role': 'user',
            'created_at': datetime.now().isoformat()
        }
        users.append(new_user)
        save_users(users)

        session['username'] = name
        session['email'] = email
        session['role'] = 'user'
        return redirect(url_for('questionnaire'))

    return render_template('register.html')

@app.route('/questionnaire', methods=['GET', 'POST'])
@login_required
def questionnaire():
    if request.method == 'POST':
        age = request.form.get('age')
        gender = request.form.get('gender')
        occupation_type = request.form.get('occupation_type')
        occupation_detail = request.form.get('occupation_detail')
        occupation = occupation_detail if occupation_type == 'Other' else occupation_type

        user_data = {
            'age': age or '',
            'gender': gender or '',
            'occupation': occupation or '',
            'timestamp': datetime.now().isoformat()
        }

        user_data_path = Path(f"instance/user_data/{session['username']}.json")
        save_json_file(user_data_path, user_data)
        return redirect(url_for('login'))

    return render_template('questionnaire.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')

        if not identifier or not password:
            flash("Please provide all credentials", "error")
            return render_template('login.html')

        users = load_users()
        user = next((u for u in users if u['email'] == identifier or u['name'] == identifier), None)

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['username'] = user['name']
            session['email'] = user['email']
            session['role'] = user.get('role', 'user')
            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif session['role'] == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            return redirect(url_for('home'))

        flash("Invalid credentials", "error")
        return render_template('login.html')

    return render_template('login.html')

@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/meditation')
@login_required
def meditation():
    return render_template('meditation.html')

@app.route('/log_meditation', methods=['POST'])
@login_required
def log_meditation():
    username = session.get('username')
    data = request.json or {}
    meditation_data = {
        'timestamp': datetime.now().isoformat(),
        'duration': data.get('duration', 300),
        'completed': data.get('completed', True)
    }

    meditation_file = Path(f"instance/meditation_data/{username}_meditation.json")
    meditation_history = load_json_file(meditation_file)
    meditation_history.append(meditation_data)
    save_json_file(meditation_file, meditation_history)

    return jsonify({
        'status': 'success',
        'message': 'Meditation session logged successfully',
        'total_sessions': len(meditation_history)
    })

@app.route('/get_meditation_stats')
@login_required
def get_meditation_stats():
    username = session.get('username')
    meditation_file = Path(f"instance/meditation_data/{username}_meditation.json")
    meditation_history = load_json_file(meditation_file)

    total_minutes = sum(session['duration'] for session in meditation_history)
    total_sessions = len(meditation_history)

    return jsonify({
        'total_minutes': total_minutes,
        'total_sessions': total_sessions,
        'recent_sessions': meditation_history[-5:]
    })

@app.route('/personal_info')
@login_required
def personal_info():
    username = session.get('username')
    user_data_path = Path(f"instance/user_data/{username}.json")
    user_data = load_json_file(user_data_path) or {
        'age': '',
        'gender': '',
        'occupation': '',
        'timestamp': datetime.now().isoformat()
    }
    return render_template('personal_info.html', user_data=user_data)

@app.route('/update_personal_info', methods=['POST'])
@login_required
def update_personal_info():
    username = session.get('username')
    user_data_path = Path(f"instance/user_data/{username}.json")
    updated_data = {
        'age': request.form.get('age', ''),
        'gender': request.form.get('gender', ''),
        'occupation': request.form.get('occupation', ''),
        'timestamp': datetime.now().isoformat()
    }
    save_json_file(user_data_path, updated_data)
    flash("Personal information updated successfully", "success")
    return redirect(url_for('personal_info'))

@app.route('/closed_ended')
@login_required
def close_ended():
    random_questions = get_random_close_questions()
    return render_template('closed_ended.html', questions=random_questions)

@app.route('/submit_close_end', methods=['POST'])
@login_required
def submit_close_ended():
    responses = [(key, value) for key, value in request.form.items()]
    username = session.get('username')
    file_path = Path(f"responses/close_ended/{username}.csv")
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Question', 'Answer'])
        writer.writerows(responses)

    return redirect(url_for('submit_opended'))

@app.route('/mood_tracker')
@login_required
def mood_tracker():
    return render_template('mood_tracker.html')

@app.route('/log_mood', methods=['POST'])
@login_required
def log_mood():
    data = request.json
    username = session.get('username')
    mood_file = Path(f"instance/mood_data/{username}_moods.json")
    moods = load_json_file(mood_file)
    moods.append({
        'mood': data.get('mood', ''),
        'timestamp': data.get('timestamp', datetime.now().isoformat())
    })
    save_json_file(mood_file, moods)
    return jsonify({'status': 'success'})

@app.route('/get_moods')
@login_required
def get_moods():
    username = session.get('username')
    mood_file = Path(f"instance/mood_data/{username}_moods.json")
    moods = load_json_file(mood_file)
    moods.sort(key=lambda x: x['timestamp'])
    return jsonify({'moods': moods})

@app.route('/open_ended', methods=['GET', 'POST'])
@login_required
def submit_opended():
    if request.method == 'POST':
        responses = {key: value for key, value in request.form.items()}
        username = session.get('username')
        file_path = Path(f"responses/open_ended/{username}.csv")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([(k, v) for k, v in responses.items()], columns=['Question', 'Response'])
        df.to_csv(file_path, mode='w', index=False)
        return redirect(url_for('thank_you'))
    random_questions = get_random_open_questions()
    return render_template('open_ended.html', questions=random_questions)

@app.route('/thank_you')
@login_required
def thank_you():
    username = session.get('username')
    close_ended_str = csv_to_string(f"responses/close_ended/{username}.csv")
    open_ended_str = csv_to_string(f"responses/open_ended/{username}.csv")

    payload = {
        "model": "gemma3n:e2b",
        "prompt": Gemini_Questionaire_prompt() + " " + close_ended_str + " " + open_ended_str,
        "system": SYSTEM_PROMPT,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        response.raise_for_status()
        judge_gemini = response.json().get('response', 'Error processing response')
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}")
        judge_gemini = f"Error: {str(e)}"

    return render_template('thank_you.html', judge_gemini=judge_gemini, user_name=username)

@app.route('/feedback')
@login_required
def feedback():
    username = session.get('username')
    user_file = Path(f"instance/user_data/{username}.json")
    user_data = load_json_file(user_file)

    if 'wellness_report' in user_data:
        judge_gemini = user_data['wellness_report']
    else:
        close_ended_str = csv_to_string(f"responses/close_ended/{username}.csv")
        open_ended_str = csv_to_string(f"responses/open_ended/{username}.csv")
        default = "This is my assessment of close-ended questions and open-ended questions. Please provide feedback on me in friendly tone in summary like a professional psychiatrist."

        payload = {
            "model": "gemma3n:e2b",
            "prompt": default + " " + close_ended_str + " " + open_ended_str,
            "system": SYSTEM_PROMPT,
            "stream": False
        }

        try:
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
            response.raise_for_status()
            judge_gemini = response.json().get('response', 'Error processing response')
            user_data['wellness_report'] = judge_gemini
            save_json_file(user_file, user_data)
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            judge_gemini = f"Error: {str(e)}"

    return render_template('thank_you.html', judge_gemini=judge_gemini, user_name=username)

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for('login'))

@app.route('/send_message')
@login_required
def send_message():
    message = request.args.get("message", "").strip()
    if not message:
        return Response("data: {'text': 'No message provided'}\n\n", content_type='text/event-stream')

    payload = {
        "model": "gemma3n:e2b",
        "prompt": message,
        "system": SYSTEM_PROMPT,
        "stream": True
    }

    def generate():
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=30)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        if "response" in chunk:
                            yield f"data: {json.dumps({'text': chunk['response']})}\n\n"
                    except json.JSONDecodeError:
                        yield f"data: {{'text': 'Decode error'}}\n\n"
        except Exception as e:
            logger.error(f"Error streaming Ollama response: {e}")
            yield f"data: {{'text': 'Error: {str(e)}'}}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), content_type="text/event-stream")

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'GET':
        return render_template('chat.html')
    data = request.get_json() or {}
    user_input = data.get('message', '')
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400

    payload = {
        "model": "gemma3n:e2b",
        "prompt": user_input,
        "system": SYSTEM_PROMPT,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        response.raise_for_status()
        bot_response = response.json().get('response', 'Error processing response')
        log_conversation(user_input, bot_response)
        return jsonify({'response': bot_response})
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/image_analysis', methods=['GET', 'POST'])
@login_required
def image_analysis():
    analysis = None
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("No file uploaded", "error")
            return redirect(request.url)

        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            flash("No file selected", "error")
            return redirect(request.url)

        if uploaded_file and allowed_file(uploaded_file.filename):
            filename = secure_filename(uploaded_file.filename)
            file_path = Path(app.config['UPLOAD_FOLDER']) / filename
            uploaded_file.save(file_path)

            with open(file_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            payload = {
                "model": "gemma3n:e2b",
                "prompt": image_prompt(),
                "system": SYSTEM_PROMPT,
                "images": [image_data],
                "stream": False
            }

            try:
                response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
                response.raise_for_status()
                analysis = response.json().get('response', 'Error processing image')
            except Exception as e:
                logger.error(f"Error analyzing image: {e}")
                analysis = f"Error: {str(e)}"
            finally:
                os.remove(file_path)

    return render_template('image_analysis.html', analysis=analysis)

@app.route('/save_rating', methods=['POST'])
@login_required
def save_rating():
    data = request.json or {}
    username = data.get('user_name', session.get('username'))
    rating = data.get('rating')

    if not rating:
        return jsonify({"success": False, "message": "Rating is required"}), 400

    ratings_data = load_json_file(RATINGS_FILE) or {"ratings": []}
    user_ratings = [r for r in ratings_data["ratings"] if r["user_name"] == username]

    new_rating = {
        "n": len(user_ratings) + 1,
        "user_name": username,
        "Wellness-rating": rating,
        "timestamp": datetime.now().isoformat()
    }

    ratings_data["ratings"].append(new_rating)
    save_json_file(RATINGS_FILE, ratings_data)

    return jsonify({"success": True, "rating_number": new_rating["n"]})

@app.route('/talk_to_me', methods=['GET', 'POST'])
@login_required
def talk_to_me():
    if request.method == 'GET':
        return render_template('talk_to_me.html')

    user_input = request.form.get('user_input', '')
    if not user_input:
        return jsonify({'error': 'No input provided'}), 400

    payload = {
        "model": "gemma3n:e2b",
        "prompt": user_input,
        "system": SYSTEM_PROMPT,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        response.raise_for_status()
        bot_response = response.json().get('response', 'Error processing response')
        log_conversation(user_input, bot_response)
        return jsonify({'response': bot_response})
    except Exception as e:
        logger.error(f"Error in talk_to_me: {e}")
        return jsonify({'error': str(e)}), 500

def log_conversation(user_input, bot_response, history_file=Path("dataset/intents.json")):
    intents_data = load_json_file(history_file) or {"intents": []}
    new_intent = {
        "patterns": [user_input],
        "responses": [bot_response],
    }
    intents_data['intents'].append(new_intent)
    save_json_file(history_file, intents_data)

# Game-related routes (simplified, with placeholders for recording)
def has_played_today(username):
    game_file = Path(f"{BASE_DIRS['game_userdata']}/{username}_game_tap_impulse.json")
    game_data = load_json_file(game_file) or {}
    today = date.today().isoformat()
    return any(session["date"] == today for sessions in game_data.values() for session in sessions)

@app.route("/game")
@login_required
def game():
    if has_played_today(session["username"]):
        flash("You have already played the game today. Come back tomorrow!", "info")
        return redirect(url_for("home"))
    return render_template("game.html")

@app.route("/game/submit", methods=["POST"])
@login_required
def submit_game_results():
    username = session.get('username')
    if has_played_today(username):
        return jsonify({"success": False, "message": "You have already played today"})

    data = request.get_json() or {}
    required_fields = ["correct_responses", "incorrect_responses", "total_time", "detailed_responses"]
    if not all(field in data for field in required_fields):
        return jsonify({"success": False, "message": "Invalid data format"})

    data["date"] = date.today().isoformat()
    game_file = Path(f"{BASE_DIRS['game_userdata']}/{username}_game_tap_impulse.json")
    game_data = load_json_file(game_file) or {}
    today = date.today().isoformat()
    game_data[today] = game_data.get(today, []) + [data]
    save_json_file(game_file, game_data)

    log_file = Path("instance/user_log.json")
    log_data = load_json_file(log_file) or {}
    log_data[username] = log_data.get(username, []) + [{
        "date": today,
        "login_time": datetime.now().isoformat(),
        "game_time": datetime.now().isoformat(),
        "game_played": True
    }]
    save_json_file(log_file, log_data)

    return jsonify({"success": True, "message": "Results saved successfully"})

@app.route("/game/analysis")
@login_required
def game_analysis():
    username = session.get('username')
    game_file = Path(f"{BASE_DIRS['game_userdata']}/{username}_game_tap_impulse.json")
    game_data = load_json_file(game_file) or {}
    all_sessions = [session for sessions in game_data.values() for session in sessions]
    analysis = {"sessions": len(all_sessions)} if all_sessions else {"message": "No game data available"}
    return render_template("game_analysis.html", analysis=analysis, username=username)

# Admin routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Access restricted. Admin privileges required.', 'error')
        return redirect(url_for('home'))

    users = load_users()
    return render_template('admin_dashboard.html', users=users, current_admin=session['email'])

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        if not all([name, email, password, role]):
            flash("All fields are required", "error")
            return render_template('create_user.html')

        users = load_users()
        if any(user['email'] == email for user in users):
            flash("Email already exists", "error")
            return render_template('create_user.html')

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        new_user = {
            'name': name,
            'email': email,
            'password': hashed_password,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'created_by': session['email']
        }
        users.append(new_user)
        save_users(users)
        flash("User created successfully", "success")
        return redirect(url_for('admin_dashboard'))

    return render_template('create_user.html')

@app.route('/admin/update_role/<user_email>', methods=['POST'])
@login_required
def update_role(user_email):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    new_role = request.form.get('new_role')
    if new_role not in ['user', 'admin', 'doctor']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    users = load_users()
    for user in users:
        if user['email'] == user_email:
            user['role'] = new_role
            user['updated_at'] = datetime.now().isoformat()
            user['updated_by'] = session['email']
            save_users(users)
            return jsonify({'success': True, 'message': 'Role updated successfully'})

    return jsonify({'success': False, 'message': 'User not found'}), 404

# Appointment routes
@app.route('/appointment')
@login_required
def appointment():
    if session.get('role') == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    return render_template('patient_dashboard.html')

@app.route('/doctor/dashboard')
@login_required
def doctor_dashboard():
    if session.get('role') != 'doctor':
        return redirect(url_for('appointment'))
    return render_template('doctor_dashboard.html')

@app.route('/api/appointments', methods=['GET', 'POST'])
@login_required
def handle_appointments():
    username = session.get('username')
    appointments_file = Path(f"instance/appointments/{username}.json")

    if request.method == 'GET':
        appointments = load_json_file(appointments_file)
        return jsonify(appointments)

    data = request.json or {}
    try:
        appointment_date = datetime.strptime(data['date'], '%Y-%m-%d')
    except (ValueError, KeyError):
        return jsonify({'error': 'Invalid date format'}), 400

    if appointment_date.weekday() >= 5:
        return jsonify({'error': 'No appointments on weekends'}), 400

    can_book, limit_message = check_appointment_limits(username, appointment_date)
    if not can_book:
        return jsonify({'error': limit_message}), 400

    appointments = load_json_file(appointments_file)
    new_appointment = {
        'id': len(appointments) + 1,
        'patient': username,
        'date': data['date'],
        'slot': data['slot'],
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'cancellation_reason': None,
        'meet_link': 'https://meet.google.com/qhe-nfdr-wvs'
    }
    appointments.append(new_appointment)
    save_json_file(appointments_file, appointments)
    update_appointment_stats(username, 'booked', appointment_date)
    send_appointment_confirmation(new_appointment)
    return jsonify(new_appointment)

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 401

    doctor_username = session.get('username')
    doctor_file = Path(f"instance/doctor_appointments/{doctor_username}.json")
    appointments_dir = Path("instance/appointments")

    for file_path in appointments_dir.glob("*.json"):
        appointments = load_json_file(file_path)
        appointment = next((a for a in appointments if a['id'] == appointment_id), None)
        if not appointment:
            continue

        appointment['status'] = request.json.get('status', 'pending')
        patient_username = file_path.stem
        patient_email = None
        users = load_users()
        user = next((u for u in users if u.get('name') == patient_username), None)
        if user:
            patient_email = user.get('email')
            appointment['patient_email'] = patient_email

        save_json_file(file_path, appointments)

        doctor_appointments = load_json_file(doctor_file)
        new_doctor_appointment = {
            'appointment_id': appointment_id,
            'patient': patient_username,
            'patient_email': patient_email,
            'date': appointment['date'],
            'slot': appointment['slot'],
            'status': appointment['status'],
            'patient_info': get_user_basic_info(patient_username),
            'updated_at': datetime.now().isoformat(),
            'meet_link': appointment['meet_link']
        }
        doctor_appointments.append(new_doctor_appointment)
        save_json_file(doctor_file, doctor_appointments)

        if appointment['status'] == 'confirmed':
            send_appointment_confirmation(appointment, patient_email)

        return jsonify({'success': True})

    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/api/appointments/cancel/<int:appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    username = session.get('username')
    appointments_file = Path(f"instance/appointments/{username}.json")
    appointments = load_json_file(appointments_file)

    appointment = next((a for a in appointments if a['id'] == appointment_id), None)
    if appointment:
        appointment['status'] = 'cancelled'
        appointment['cancellation_reason'] = request.json.get('reason')
        appointment_date = datetime.strptime(appointment['date'], '%Y-%m-%d')
        update_appointment_stats(username, 'cancelled', appointment_date)
        save_json_file(appointments_file, appointments)
        return jsonify({'success': True})

    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/api/user/stats', methods=['GET'])
@login_required
def get_user_stats():
    username = session.get('username')
    stats_file = Path(f"instance/appointment_stats/{username}.json")
    return jsonify(load_json_file(stats_file) or {
        'total_appointments': 0,
        'total_cancellations': 0,
        'yearly_stats': {},
        'monthly_stats': {},
        'rating': 'white'
    })

@app.route('/api/available-slots', methods=['GET'])
@login_required
def get_available_slots():
    return jsonify(['10:00-11:00', '12:00-13:00', '15:00-16:00', '17:00-18:00'])

@app.route('/api/doctor/patient-info/<username>', methods=['GET'])
@login_required
def get_patient_info(username):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 401

    return jsonify({
        'basic_info': get_user_basic_info(username),
        'appointment_history': get_appointment_history(username),
        'mood_history': get_mood_history(username),
        'questionnaire_responses': get_questionnaire_responses(username)
    })

def check_appointment_limits(username, appointment_date):
    appointments_file = Path(f"instance/appointments/{username}.json")
    appointments = load_json_file(appointments_file)

    week_start = appointment_date - timedelta(days=appointment_date.weekday())
    week_end = week_start + timedelta(days=6)
    week_appointments = [a for a in appointments
                        if week_start <= datetime.strptime(a['date'], '%Y-%m-%d') <= week_end
                        and a['status'] != 'cancelled']
    if len(week_appointments) >= 1:
        return False, "Weekly limit reached (maximum 1 appointment per week)"

    month_start = appointment_date.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    month_appointments = [a for a in appointments
                         if month_start <= datetime.strptime(a['date'], '%Y-%m-%d') <= month_end
                         and a['status'] != 'cancelled']
    if len(month_appointments) >= 4:
        return False, "Monthly limit reached (maximum 4 appointments per month)"

    return True, None

def update_appointment_stats(username, action, appointment_date):
    stats_file = Path(f"instance/appointment_stats/{username}.json")
    stats = load_json_file(stats_file) or {
        'total_appointments': 0,
        'total_cancellations': 0,
        'yearly_stats': {},
        'monthly_stats': {},
        'rating': 'white'
    }

    year = str(appointment_date.year)
    month = str(appointment_date.month)

    stats['yearly_stats'].setdefault(year, {'booked': 0, 'cancelled': 0})
    stats['monthly_stats'].setdefault(month, {'booked': 0, 'cancelled': 0})

    if action == 'booked':
        stats['total_appointments'] += 1
        stats['yearly_stats'][year]['booked'] += 1
        stats['monthly_stats'][month]['booked'] += 1
    elif action == 'cancelled':
        stats['total_cancellations'] += 1
        stats['yearly_stats'][year]['cancelled'] += 1
        stats['monthly_stats'][month]['cancelled'] += 1

    monthly_cancel_rate = stats['monthly_stats'][month]['cancelled'] / max(stats['monthly_stats'][month]['booked'], 1)
    stats['rating'] = 'blue' if monthly_cancel_rate < 0.1 else 'red' if monthly_cancel_rate > 0.4 else 'white'

    save_json_file(stats_file, stats)

def get_user_basic_info(username):
    user_data_path = Path(f"instance/user_data/{username}.json")
    return load_json_file(user_data_path) or {
        'age': 'Unknown',
        'gender': 'Unknown',
        'occupation': 'Unknown'
    }

def get_appointment_history(username):
    appointments_file = Path(f"instance/appointments/{username}.json")
    return load_json_file(appointments_file)

def get_mood_history(username):
    mood_file = Path(f"instance/mood_data/{username}_moods.json")
    return load_json_file(mood_file)

def get_questionnaire_responses(username):
    responses = {'close_ended': [], 'open_ended': []}
    try:
        with open(f"responses/close_ended/{username}.csv", 'r') as f:
            reader = csv.DictReader(f)
            responses['close_ended'] = list(reader)
    except FileNotFoundError:
        pass
    try:
        with open(f"responses/open_ended/{username}.csv", 'r') as f:
            reader = csv.DictReader(f)
            responses['open_ended'] = list(reader)
    except FileNotFoundError:
        pass
    return responses

def send_appointment_confirmation(appointment_data, recipient_email=None):
    username = appointment_data.get('patient')
    if not recipient_email:
        users = load_users()
        user = next((u for u in users if u.get('name') == username), None)
        if user:
            recipient_email = user.get('email')
        else:
            logger.error(f"Could not find email for user: {username}")
            return False

    msg = MIMEMultipart()
    msg['From'] = app.config['MAIL_USERNAME']
    msg['To'] = recipient_email
    msg['Subject'] = "Your Appointment Confirmation"

    body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px; }}
        .email-container {{ max-width: 600px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1); margin: auto; }}
        h2 {{ color: #333; text-align: center; }}
        p {{ font-size: 16px; color: #555; line-height: 1.5; }}
        .appointment-details {{ background: #eaf5ff; padding: 10px; border-left: 4px solid #007bff; margin: 15px 0; }}
        .appointment-details strong {{ color: #007bff; }}
        .join-button {{ display: inline-block; background: #007bff; color: white; text-decoration: none; padding: 10px 15px; border-radius: 5px; font-weight: bold; margin-top: 10px; }}
        .join-button:hover {{ background: #0056b3; }}
        .footer {{ font-size: 14px; color: #777; margin-top: 20px; text-align: center; }}
    </style>
</head>
<body>
    <div class="email-container">
        <h2>Appointment Confirmation</h2>
        <p>Dear <strong>{username}</strong>,</p>
        <p>Your appointment has been scheduled for:</p>
        <div class="appointment-details">
            <p><strong>Date:</strong> {appointment_data['date']}</p>
            <p><strong>Time:</strong> {appointment_data['slot']}</p>
            <p><strong>Join Link:</strong> <a href="{appointment_data['meet_link']}">{appointment_data['meet_link']}</a></p>
        </div>
        <p>Click below to join your appointment:</p>
        <p><a href="{appointment_data['meet_link']}" class="join-button">Join Here</a></p>
        <p>Please arrive 10 minutes before your scheduled time.</p>
        <p>If you need to cancel or reschedule, please do so at least 24 hours in advance.</p>
        <p class="footer">Thank you!</p>
    </div>
</body>
</html>
"""
    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        logger.info(f"Appointment confirmation email sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

# Initialize directories
ensure_directories()

if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)