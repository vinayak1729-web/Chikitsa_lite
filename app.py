from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response, flash, Blueprint, send_file
import json
import os
import secrets
from datetime import datetime, date, timedelta
from pathlib import Path
import bcrypt
import pandas as pd
import requests
import base64
import re
import io
from functools import wraps
import logging
import cv2
from fer import FER
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pytz
import csv

# ReportLab imports
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

# Import modules
from Create_modules.open_end_questions import get_random_open_questions
from Create_modules.close_end_questionaire import get_random_close_questions
from Create_modules.csv_extracter import close_ended_response, open_ended_response, csv_to_string

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=1800
)

# Ollama API configuration for gemma3n model
OLLAMA_API_URL = "http://localhost:11434/api/generate"
SYSTEM_PROMPT = """
You are Seraphis, an empathetic AI psychiatrist, providing mental health support using evidence-based coping strategies, behaving like a best friend, showing love, care, and secular Bhagavad Gita lessons (e.g., focus on the present, detachment from outcomes) tailored to users' emotional needs. Acknowledge feelings, assess concerns, suggest actionable techniques, and recommend professional help for severe symptoms. Use a warm, inclusive tone, avoid religious references, and encourage gradual progress. Format your responses in markdown for clear presentation.
"""

# Directory setup
BASE_DIRS = {
    "users": "instance/users",
    "wellness": "instance/wellness",
    "responses_close": "responses/close_ended",
    "responses_open": "responses/open_ended",
    "game_userdata": "instance/game/userdata",
    "game_video": "instance/game/video",
    "game_audio": "instance/game/audio",
    "user_data": "instance/user_data",
    "mood_data": "instance/mood_data",
    "meditation_data": "instance/meditation_data",
    "appointments": "instance/appointments",
    "appointment_stats": "instance/appointment_stats",
    "doctor_appointments": "instance/doctor_appointments",
    "ratings": "instance/rating"
}

for dir_path in BASE_DIRS.values():
    os.makedirs(dir_path, exist_ok=True)

# Configure upload folder and allowed extensions for image analysis
UPLOAD_FOLDER = 'image_analysis/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    """Checks if the file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# User data helper functions
USERS_FILE = os.path.join(BASE_DIRS["users"], "users.json")

def manage_user_data(action, username=None, user_data=None):
    """Manage user data in JSON file with error handling."""
    try:
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, "w") as f:
                json.dump({"users": []}, f, indent=4)

        with open(USERS_FILE, "r") as f:
            db = json.load(f)

        if isinstance(db, list):
            db = {"users": db}

        if action == "read":
            return True, next((u for u in db["users"] if u["username"] == username), {}) if username else db
        elif action == "write":
            if not user_data:
                return False, "No user data provided"
            if any(u["email"] == user_data["email"] for u in db["users"]):
                return False, "Email already registered"
            if any(u["username"] == user_data["username"] for u in db["users"]):
                return False, "Username already exists"
            db["users"].append(user_data)
            with open(USERS_FILE, "w") as f:
                json.dump(db, f, indent=4)
            return True, "User registered"
        return False, "Invalid action"
    except json.JSONDecodeError:
        return False, "Corrupted user database"
    except IOError as e:
        return False, f"File access error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def load_users():
    """Load users from the JSON file."""
    try:
        success, data = manage_user_data("read")
        if success:
            return data["users"]
        return []
    except:
        return []

def save_users(users):
    """Save users to the JSON file."""
    with open(USERS_FILE, "w") as f:
        json.dump({"users": users}, f, indent=4)

# Wellness helper functions
def get_wellness_file(username):
    """Return path to user's wellness file."""
    return os.path.join(BASE_DIRS["wellness"], f"{username}.json")

def load_wellness_data(username):
    """Load user's wellness data with fallback."""
    file_path = get_wellness_file(username)
    if not os.path.exists(file_path):
        return {"questionnaire": {"close_ended": [], "open_ended": []}, "wellness_report": ""}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"questionnaire": {"close_ended": [], "open_ended": []}, "wellness_report": ""}

def save_wellness_data(username, questionnaire=None, wellness_report=None):
    """Save user's wellness data with error handling."""
    data = load_wellness_data(username)
    if questionnaire:
        data["questionnaire"].update({k: v for k, v in questionnaire.items() if k in ["close_ended", "open_ended"]})
    if wellness_report is not None:
        data["wellness_report"] = wellness_report
    try:
        with open(get_wellness_file(username), "w") as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        flash(f"Failed to save wellness data: {str(e)}", "error")

# Password helper functions
def hash_password(password):
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# Validation helper functions
def validate_email(email):
    """Validate email format using regex."""
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))

def validate_password(password):
    """Validate password strength (min 8 chars, uppercase, digit)."""
    return len(password) >= 8 and any(c.isupper() for c in password) and any(c.isdigit() for c in password)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Gemma chat function using Ollama API
def gemma_chat(user_input, system_prompt=None):
    """Chat with gemma3n model via Ollama API."""
    try:
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT
            
        payload = {
            "model": "gemma3n:e2b",
            "prompt": user_input,
            "system": system_prompt,
            "stream": False
        }
        
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "I'm having trouble generating a response. Please try again.")
        
    except Exception as e:
        logging.error(f"Error in gemma_chat: {str(e)}")
        return "I'm experiencing technical difficulties. Please try again later."

# Routes from old app.py
@app.route('/')
def index():
    """Main index page - redirect to login if not logged in."""
    if 'username' in session:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with validation."""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()  # Can be email or username
        password = request.form.get("password", "").strip()
        
        if not all([identifier, password]):
            flash("Email/Username and password are required", "error")
        else:
            success, result = manage_user_data("read")
            if success:
                for user in result["users"]:
                    # Check both email and username
                    if (user["email"] == identifier or user.get("username") == identifier) and check_password(password, user["password"]):
                        session["username"] = user.get("username", user.get("name"))
                        session["email"] = user["email"]
                        session["role"] = user.get("role", "user")
                        session.permanent = True
                        
                        # Redirect based on role
                        if session['role'] == 'admin':
                            return redirect(url_for('admin_dashboard'))
                        elif session['role'] == 'doctor':
                            return redirect(url_for('doctor_dashboard'))
                        else:
                            return redirect(url_for('home'))
                            
                flash("Invalid credentials", "error")
            else:
                flash(result, "error")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration with validation."""
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        if not all([email, password, name]):
            flash("All required fields must be filled", "error")
        elif not validate_email(email):
            flash("Invalid email format", "error")
        elif not validate_password(password):
            flash("Password must be at least 8 characters with an uppercase letter and a digit", "error")
        else:
            # Generate username from email
            username = email.split("@")[0]
            success, existing_users = manage_user_data("read")
            if success:
                existing_usernames = [u.get("username", u.get("name")) for u in existing_users["users"]]
                base_username = username
                counter = 1
                while username in existing_usernames:
                    username = f"{base_username}{counter}"
                    counter += 1
                    
                user_data = {
                    "username": username,
                    "name": name,  # Keep for compatibility
                    "email": email,
                    "password": hash_password(password),
                    "role": "user",
                    "created_at": datetime.now().isoformat()
                }
                
                success, message = manage_user_data("write", user_data=user_data)
                if success:
                    flash("Registration successful! Please log in.", "success")
                    return redirect(url_for("login"))
                flash(message, "error")
            else:
                flash("Registration failed. Please try again.", "error")
        return redirect(url_for("register"))
    return render_template("register.html")

@app.route('/questionnaire', methods=['GET', 'POST'])
@login_required
def questionnaire():
    """Handle user questionnaire data."""
    if request.method == 'POST':
        age = request.form.get('age')
        gender = request.form.get('gender')
        occupation_type = request.form.get('occupation_type')
        occupation_detail = request.form.get('occupation_detail')
        occupation = occupation_detail if occupation_type == 'Other' else occupation_type
        
        username = session.get('username')
        user_data = {
            'age': age,
            'gender': gender,
            'occupation': occupation,
            'timestamp': datetime.now().isoformat()
        }
        
        filename = f"{BASE_DIRS['user_data']}/{username}.json"
        with open(filename, 'w') as f:
            json.dump(user_data, f, indent=4)
            
        return redirect(url_for('home'))
        
    return render_template('questionnaire.html')

@app.route('/home')
@login_required
def home():
    """Render home page with authentication."""
    return render_template("home.html", username=session["username"])

@app.route('/meditation')
@login_required
def meditation():
    """Render meditation page."""
    return render_template('meditation.html')

@app.route('/log_meditation', methods=['POST'])
@login_required
def log_meditation():
    """Log meditation session data."""
    username = session.get('username')
    
    meditation_data = {
        'timestamp': datetime.now().isoformat(),
        'duration': request.json.get('duration', 300),  # Default 5 minutes
        'completed': request.json.get('completed', True)
    }
    
    meditation_file = f'{BASE_DIRS["meditation_data"]}/{username}_meditation.json'
    
    try:
        with open(meditation_file, 'r') as f:
            meditation_history = json.load(f)
    except FileNotFoundError:
        meditation_history = []
    
    meditation_history.append(meditation_data)
    
    with open(meditation_file, 'w') as f:
        json.dump(meditation_history, f, indent=4)
    
    return jsonify({
        'status': 'success',
        'message': 'Meditation session logged successfully',
        'total_sessions': len(meditation_history)
    })

@app.route('/get_meditation_stats')
@login_required
def get_meditation_stats():
    """Get meditation statistics for user."""
    username = session.get('username')
    meditation_file = f'{BASE_DIRS["meditation_data"]}/{username}_meditation.json'
    
    try:
        with open(meditation_file, 'r') as f:
            meditation_history = json.load(f)
            
        total_minutes = sum(session['duration'] for session in meditation_history)
        total_sessions = len(meditation_history)
        
        return jsonify({
            'total_minutes': total_minutes,
            'total_sessions': total_sessions,
            'recent_sessions': meditation_history[-5:]  # Last 5 sessions
        })
    except FileNotFoundError:
        return jsonify({
            'total_minutes': 0,
            'total_sessions': 0,
            'recent_sessions': []
        })

@app.route('/personal_info')
@login_required
def personal_info():
    """Display personal information page."""
    username = session.get('username')
    user_data_path = f'{BASE_DIRS["user_data"]}/{username}.json'
    
    if os.path.exists(user_data_path):
        with open(user_data_path, 'r') as f:
            user_data = json.load(f)
    else:
        user_data = {
            "age": "",
            "gender": "",
            "occupation": "",
            "timestamp": datetime.now().isoformat()
        }
    
    return render_template('personal_info.html', user_data=user_data)

@app.route('/update_personal_info', methods=['POST'])
@login_required
def update_personal_info():
    """Update personal information."""
    username = session.get('username')
    user_data_path = f'{BASE_DIRS["user_data"]}/{username}.json'
    
    updated_data = {
        "age": request.form.get('age'),
        "gender": request.form.get('gender'),
        "occupation": request.form.get('occupation'),
        "timestamp": datetime.now().isoformat()
    }
    
    with open(user_data_path, 'w') as f:
        json.dump(updated_data, f, indent=4)
    
    return redirect(url_for('personal_info'))

@app.route('/mood_tracker')
@login_required
def mood_tracker():
    """Render mood tracker page."""
    return render_template('mood_tracker.html')

@app.route('/log_mood', methods=['POST'])
@login_required
def log_mood():
    """Log mood data."""
    data = request.json
    username = session.get('username')
    mood_file = f'{BASE_DIRS["mood_data"]}/{username}_moods.json'
    
    try:
        with open(mood_file, 'r') as f:
            moods = json.load(f)
    except FileNotFoundError:
        moods = []
    
    moods.append({
        'mood': data['mood'],
        'timestamp': data['timestamp']
    })
    
    with open(mood_file, 'w') as f:
        json.dump(moods, f)
    
    return jsonify({'status': 'success'})

@app.route('/get_moods')
@login_required
def get_moods():
    """Get mood history for user."""
    username = session.get('username')
    mood_file = f'{BASE_DIRS["mood_data"]}/{username}_moods.json'
    
    try:
        with open(mood_file, 'r') as f:
            moods = json.load(f)
            moods.sort(key=lambda x: x['timestamp'])
            return jsonify({'moods': moods})
    except FileNotFoundError:
        return jsonify({'moods': []})

# Questionnaire routes
@app.route('/closed_ended')
@login_required
def close_ended():
    """Handle close-ended questionnaire."""
    random_questions = get_random_close_questions()[:5]
    return render_template('closed_ended.html', questions=random_questions)

@app.route('/submit_close_end', methods=['POST'])
@login_required
def submit_close_ended():
    """Submit close-ended questionnaire responses."""
    if request.method == 'POST':
        responses = []
        for question in request.form:
            answer = request.form[question]
            responses.append((question, answer))
        
        # Save responses to CSV
        save_to_csv(responses, 'close_ended')
        
        # Save to wellness data
        response_data = [{"question": q, "answer": a} for q, a in responses]
        save_wellness_data(session["username"], questionnaire={"close_ended": response_data})
        
        return redirect(url_for('open_ended'))

@app.route('/open_ended', methods=['GET', 'POST'])
@login_required
def open_ended():
    """Handle open-ended questionnaire."""
    if request.method == 'POST':
        responses = {key: value for key, value in request.form.items()}
        save_responses_to_csv(responses)
        
        # Save to wellness data
        response_data = [{"question": q, "answer": a} for q, a in responses.items()]
        save_wellness_data(session["username"], questionnaire={"open_ended": response_data})
        
        return redirect(url_for('thank_you'))
    else:
        random_questions = get_random_open_questions()[:10]
        return render_template('open_ended.html', questions=random_questions)

def save_to_csv(responses, response_type):
    """Save responses to CSV file."""
    username = session.get('username')
    if not username:
        return
    
    file_path = f'{BASE_DIRS[f"responses_{response_type}"]}/{username}.csv'
    
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Question', 'Answer'])
        for response in responses:
            writer.writerow(response)

def save_responses_to_csv(responses):
    """Save open-ended responses to CSV."""
    username = session.get('username')
    if not username:
        return
    
    file_path = f'{BASE_DIRS["responses_open"]}/{username}.csv'
    
    data_to_save = [(question, responses[question]) for question in responses]
    df = pd.DataFrame(data_to_save, columns=['Question', 'Response'])
    df.to_csv(file_path, mode='w', index=False)

@app.route('/thank_you')
@login_required
def thank_you():
    """Display thank you page with wellness analysis."""
    username = session.get('username')
    
    # Read from user-specific files
    close_ended_str = csv_to_string(f"{BASE_DIRS['responses_close']}/{username}.csv")
    open_ended_str = csv_to_string(f"{BASE_DIRS['responses_open']}/{username}.csv")
    
    questionnaire_prompt = """
    This is my assessment of close-ended questions and open-ended questions. Please provide feedback on me in friendly tone in summary like a professional psychiatrist, in english or hinglish or Minglish. Analyze the responses and provide mental health insights, coping strategies, and recommendations for improvement.
    """
    
    judge_gemini = gemma_chat(questionnaire_prompt + " " + close_ended_str + " " + open_ended_str)
    
    # Save the wellness report
    save_wellness_data(username, wellness_report=judge_gemini)
    
    return render_template('thank_you.html', judge_gemini=judge_gemini, user_name=username, completejudege=judge_gemini)

@app.route('/feedback')
@login_required
def feedback():
    """Display feedback/wellness report."""
    username = session.get('username')
    user_file = f'{BASE_DIRS["user_data"]}/{username}.json'
    
    try:
        with open(user_file, 'r') as f:
            user_data = json.load(f)
            
        if 'wellness_report' in user_data:
            judge_gemini = user_data['wellness_report']
        else:
            # Generate new report
            close_ended_str = csv_to_string(f"{BASE_DIRS['responses_close']}/{username}.csv")
            open_ended_str = csv_to_string(f"{BASE_DIRS['responses_open']}/{username}.csv")
            
            default = "This is my assessment of close-ended questions and open-ended questions. Please provide feedback on me in friendly tone in summary like a professional psychiatrist."
            judge_gemini = gemma_chat(default + " " + close_ended_str + " " + open_ended_str)
            
            user_data['wellness_report'] = judge_gemini
            
            with open(user_file, 'w') as f:
                json.dump(user_data, f, indent=4)
    
    except FileNotFoundError:
        close_ended_str = csv_to_string(f"{BASE_DIRS['responses_close']}/{username}.csv")
        open_ended_str = csv_to_string(f"{BASE_DIRS['responses_open']}/{username}.csv")
        
        default = "This is my assessment of close-ended questions and open-ended questions. Please provide feedback on me in friendly tone in summary like a professional psychiatrist."
        judge_gemini = gemma_chat(default + " " + close_ended_str + " " + open_ended_str)
        
        user_data = {
            "age": "",
            "gender": "",
            "occupation": "",
            "timestamp": datetime.now().isoformat(),
            "wellness_report": judge_gemini
        }
        
        with open(user_file, 'w') as f:
            json.dump(user_data, f, indent=4)
    
    return render_template('thank_you.html', 
                         judge_gemini=judge_gemini, 
                         user_name=username, 
                         completejudege=judge_gemini)

# Chat routes
@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    """Handle chat interactions."""
    if request.method == 'GET':
        return render_template('chat.html')
    elif request.method == 'POST':
        try:
            data = request.get_json()
            user_input = data.get('message')
            response = gemma_chat(user_input)
            return jsonify({'response': response})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route("/consultation")
@login_required
def consultation():
    """Render consultation page with authentication."""
    return render_template("consultation.html")

@app.route("/send_message", methods=["POST"])
@login_required
def send_message():
    """Stream AI response for user messages."""
    if "message" not in request.form:
        return Response("data: {'text': 'No message provided'}\n\n", content_type='text/event-stream')

    user_message = request.form["message"].strip()
    files = request.files.getlist("files")
    images = [base64.b64encode(file.read()).decode("utf-8") for file in files if file]

    payload = {"model": "gemma3n:e2b", "prompt": user_message, "system": SYSTEM_PROMPT, "stream": True, "images": images}

    def generate():
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, stream=True)
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
            yield f"data: {{'text': 'Error: {str(e)}'}}\n\n"
        yield "data: [DONE]\n\n"
    return Response(generate(), content_type="text/event-stream")

# Wellness report routes
@app.route("/wellness_report")
@login_required
def wellness_report():
    """Generate and display wellness report."""
    username = session["username"]
    close_responses = close_ended_response(username)
    open_responses = open_ended_response(username)
    
    prompt = f"Analyze the following responses and generate a wellness report.\n### Close-Ended Responses\n{close_responses}\n### Open-Ended Responses\n{open_responses}"
    
    if request.headers.get("Accept") == "text/event-stream":
        payload = {"model": "gemma3n:e2b", "prompt": prompt, "system": SYSTEM_PROMPT, "stream": True}

        def generate():
            try:
                response = requests.post(OLLAMA_API_URL, json=payload, stream=True)
                response.raise_for_status()
                report = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode("utf-8"))
                            if "response" in chunk:
                                report += chunk["response"]
                                yield f"data: {json.dumps({'text': chunk['response']})}\n\n"
                        except json.JSONDecodeError:
                            yield f"data: {{'text': 'Decode error'}}\n\n"
                if report:
                    save_wellness_data(username, wellness_report=report)
            except Exception as e:
                yield f"data: {{'text': 'Error: {str(e)}'}}\n\n"
            yield "data: [DONE]\n\n"
        
        return Response(generate(), content_type="text/event-stream")
    
    data = load_wellness_data(username)
    return render_template("wellness_report.html", wellness_report=data.get("wellness_report", "Report not available."))

@app.route("/wellness_journey")
@login_required
def wellness_journey():
    """Display wellness journey with authentication."""
    username = session["username"]
    data = load_wellness_data(username)
    return render_template("wellness_journey.html", user_data={"username": username}, wellness_report=data.get("wellness_report", "Not available."))

# Game-related helper functions
def ensure_directory_exists(directory):
    """Create directory if it doesn't exist."""
    os.makedirs(directory, exist_ok=True)

def read_json_file(filepath):
    """Read JSON file with error handling."""
    try:
        return json.load(open(filepath, "r")) if os.path.exists(filepath) else {}
    except (json.JSONDecodeError, IOError):
        return {}

def write_json_file(filepath, data):
    """Write data to JSON file with error handling."""
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except IOError:
        return False

def has_played_today(username):
    """Check if user has played the game today."""
    log_file = os.path.join("instance", "user_log.json")
    log_data = read_json_file(log_file)
    today = date.today().isoformat()
    return username in log_data and any(log_entry.get("date") == today and log_entry.get("game_played") for log_entry in log_data[username])

def log_game_session(username):
    """Log user's game session."""
    log_file = os.path.join("instance", "user_log.json")
    ensure_directory_exists("instance")
    log_data = read_json_file(log_file)
    log_data.setdefault(username, [])
    today = date.today().isoformat()
    current_time = datetime.now().isoformat()

    for log_entry in log_data[username]:
        if log_entry.get("date") == today:
            log_entry.update({"game_played": True, "game_time": current_time})
            write_json_file(log_file, log_data)
            return
    log_data[username].append({
        "date": today,
        "login_time": current_time,
        "game_played": True,
        "game_time": current_time
    })
    write_json_file(log_file, log_data)

def save_game_results(username, results):
    """Save game results to user's data file."""
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    game_data = read_json_file(game_file)
    today = date.today().isoformat()
    current_time = datetime.now().isoformat()
    game_data.setdefault(today, [])
    results.update({"timestamp": current_time, "date": today})
    game_data[today].append(results)
    return write_json_file(game_file, game_data)

def save_recording(username, file, file_type):
    """Save video or audio recording with timestamp and error handling."""
    try:
        if not file or not hasattr(file, 'filename') or not file.filename:
            return None
            
        directory = BASE_DIRS[f"game_{file_type}"]
        ensure_directory_exists(directory)
        
        # Generate safe filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_username = re.sub(r'\W+', '', username)
        filename = f"{safe_username}_{timestamp}.{file_type}"
        filepath = os.path.join(directory, filename)
        
        # Save file
        file.save(filepath)
        
        # Verify file was saved
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return filename
        return None
    except Exception as e:
        app.logger.error(f"Error saving {file_type} recording: {str(e)}")
        return None

def analyze_performance(username):
    """Analyze user's game performance and provide insights."""
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    game_data = read_json_file(game_file)

    if not game_data:
        return {"message": "No game data available for analysis"}

    all_sessions = [session for sessions in game_data.values() for session in sessions]
    if not all_sessions:
        return {"message": "No game sessions found"}

    total_sessions = len(all_sessions)
    total_correct = sum(session.get("correct_responses", 0) for session in all_sessions)
    total_incorrect = sum(session.get("incorrect_responses", 0) for session in all_sessions)
    total_responses = total_correct + total_incorrect

    if total_responses == 0:
        return {"message": "No responses recorded"}

    accuracy = (total_correct / total_responses) * 100
    correct_times = [r.get("reaction_time", 0) for session in all_sessions for r in session.get("detailed_responses", []) if r.get("correct")]
    incorrect_times = [r.get("reaction_time", 0) for session in all_sessions for r in session.get("detailed_responses", []) if not r.get("correct")]

    avg_correct_time = sum(correct_times) / len(correct_times) if correct_times else 0
    avg_incorrect_time = sum(incorrect_times) / len(incorrect_times) if incorrect_times else 0

    insights = []
    if accuracy >= 90:
        insights.append("Excellent attention control and cognitive inhibition!")
    elif accuracy >= 75:
        insights.append("Good focus, but there's room for improvement in impulse control.")
    else:
        insights.append("Consider practicing mindfulness to improve attention and reduce impulsivity.")
    if avg_incorrect_time < avg_correct_time and avg_incorrect_time > 0:
        insights.append("You tend to respond too quickly to mismatches. Practice taking a moment to process.")
    if avg_correct_time > 800:
        insights.append("Reaction times suggest possible fatigue or stress. Take breaks and relax.")
    elif avg_correct_time < 400:
        insights.append("Fast reaction times indicate good cognitive processing speed!")

    return {
        "total_sessions": total_sessions,
        "accuracy": round(accuracy, 2),
        "total_correct": total_correct,
        "total_incorrect": total_incorrect,
        "avg_correct_time": round(avg_correct_time, 2),
        "avg_incorrect_time": round(avg_incorrect_time, 2),
        "insights": insights,
        "game_data": game_data
    }

def generate_pdf_report(username, analysis_data):
    """Generate a PDF report of user's game analysis with error handling."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        name="CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph("Tap-Impulse Test Analysis Report", title_style))
    story.append(Paragraph(f"User: {username}", styles["Heading2"]))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Performance Summary", styles["Heading2"]))
    summary_data = [
        ["Metric", "Value"],
        ["Total Sessions", str(analysis_data.get("total_sessions", 0))],
        ["Overall Accuracy", f"{analysis_data.get('accuracy', 0)}%"],
        ["Correct Responses", str(analysis_data.get("total_correct", 0))],
        ["Incorrect Responses", str(analysis_data.get("total_incorrect", 0))],
        ["Avg Correct Response Time", f"{analysis_data.get('avg_correct_time', 0)} ms"],
        ["Avg Incorrect Response Time", f"{analysis_data.get('avg_incorrect_time', 0)} ms"]
    ]
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Insights & Recommendations", styles["Heading2"]))
    for insight in analysis_data.get("insights", []):
        story.append(Paragraph(f"• {insight}", styles["Normal"]))
        story.append(Spacer(1, 6))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Session History", styles["Heading2"]))
    game_data = analysis_data.get("game_data", {})
    for date_key, sessions in game_data.items():
        story.append(Paragraph(f"Date: {date_key}", styles["Heading3"]))
        for i, session in enumerate(sessions, 1):
            session_text = f"Session {i}: {session.get('correct_responses', 0)} correct, {session.get('incorrect_responses', 0)} incorrect"
            story.append(Paragraph(session_text, styles["Normal"]))
        story.append(Spacer(1, 10))

    try:
        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        flash(f"Failed to generate PDF report: {str(e)}", "error")
        return io.BytesIO()

# Game routes
@app.route("/game")
@login_required
def game():
    """Main game route with authentication."""
    username = session["username"]
    if has_played_today(username):
        flash("You have already played the game today. Come back tomorrow!", "info")
        return redirect(url_for("home"))
    return render_template("game.html")

@app.route("/game/submit", methods=["POST"])
@login_required
def submit_game_results():
    """Submit game results and recordings."""
    username = session["username"]
    if has_played_today(username):
        return jsonify({"success": False, "message": "You have already played today"})

    data = request.get_json()
    required_fields = ["correct_responses", "incorrect_responses", "total_time", "detailed_responses"]
    if not all(field in data for field in required_fields):
        return jsonify({"success": False, "message": "Invalid data format"})

    video_file = request.files.get("video")
    audio_file = request.files.get("audio")
    if video_file:
        data["video_recording"] = save_recording(username, video_file, "video")
    if audio_file:
        data["audio_recording"] = save_recording(username, audio_file, "audio")

    if save_game_results(username, data):
        log_game_session(username)
        return jsonify({
            "success": True,
            "message": "Results and recordings saved successfully",
            "video": data.get("video_recording"),
            "audio": data.get("audio_recording")
        })
    return jsonify({"success": False, "message": "Failed to save results"})

@app.route("/game/analysis")
@login_required
def game_analysis():
    """Show game analysis with authentication."""
    username = session["username"]
    analysis = analyze_performance(username)
    return render_template("game_analysis.html", analysis=analysis, username=username)

@app.route("/game/download-report")
@login_required
def download_report():
    """Download PDF report with authentication."""
    username = session["username"]
    analysis = analyze_performance(username)
    if "message" in analysis and "No game data" in analysis["message"]:
        flash("No game data available for report generation", "error")
        return redirect(url_for("game_analysis"))
    pdf_buffer = generate_pdf_report(username, analysis)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{username}_tap_impulse_analysis_{date.today().isoformat()}.pdf",
        mimetype="application/pdf"
    )

@app.route("/api/game/data")
@login_required
def get_game_data():
    """API endpoint to get game data with authentication."""
    username = session["username"]
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    return jsonify(read_json_file(game_file))

# Image analysis routes
@app.route('/image_analysis', methods=['GET', 'POST'])
@login_required
def image_analysis():
    """Handle image analysis using gemma3n model."""
    analysis = None
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(request.url)

        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)

        if uploaded_file and allowed_file(uploaded_file.filename):
            try:
                # Process the uploaded image
                image_data = uploaded_file.read()
                
                # Convert image to base64 for analysis
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                
                # Create analysis prompt for medical/health images
                image_prompt = """
                <instructions>
                You are CHIKITSA (Cognitive Health Intelligence Knowledge with Keen Interactive Treatment Support from AI), an AI combining the expertise of a compassionate digital psychiatrist and a skilled medical practitioner specializing in image analysis. Your role is to provide mental health support and analyze medical images (e.g., scans, reports) for a renowned hospital, ensuring empathetic, evidence-based, and inclusive responses. For mental health concerns (from user input or inferred from images), offer coping strategies and integrate practical, knowledge-based lessons from the Bhagavad Gita, focusing solely on psychological/philosophical insights and avoiding religious or spiritual references unless explicitly requested. For medical images, identify health issues, suggest next steps, and recommend consulting a doctor without prescribing remedies. Always recommend meditation and low-intensity exercise to support mental and physical well-being, tailoring suggestions to the user's context. Respond in English, or optionally Hinglish or Minglish (Marathi-English mix) for cultural engagement, maintaining a friendly, professional tone. Structure your responses clearly, ensuring sensitivity to the user's emotional and physical state.

                Please analyze this medical image/report and provide:
                1. Observations about what you can see
                2. Possible health implications
                3. Recommendations for next steps
                4. Mental health support if the findings might cause anxiety
                5. Always include: "Consult with a Doctor before making any decisions"
                </instructions>
                """
                
                # Use gemma chat for analysis
                analysis = gemma_chat(f"Please analyze this medical image: {image_prompt}", image_prompt)
                
            except Exception as e:
                flash(f'Error analyzing image: {str(e)}', 'error')
                analysis = None
        else:
            flash('Invalid file format. Please upload PNG, JPG, JPEG, or GIF files.', 'error')
    
    return render_template('image_analysis.html', analysis=analysis)

# Rating system
def load_ratings():
    """Load ratings from JSON file."""
    ratings_file = Path(f'{BASE_DIRS["ratings"]}/ratings.json')
    if ratings_file.exists():
        with open(ratings_file, 'r') as f:
            return json.load(f)
    return {"ratings": []}

def save_ratings(ratings_data):
    """Save ratings to JSON file."""
    ratings_file = Path(f'{BASE_DIRS["ratings"]}/ratings.json')
    with open(ratings_file, 'w') as f:
        json.dump(ratings_data, f, indent=4)

@app.route('/save_rating', methods=['POST'])
@login_required
def save_rating():
    """Save user rating."""
    data = request.json
    ratings_data = load_ratings()
    
    user_ratings = [r for r in ratings_data["ratings"] if r["user_name"] == data["user_name"]]
    
    new_rating = {
        "n": len(user_ratings) + 1,
        "user_name": data["user_name"],
        "Wellness-rating": data["rating"],
        "timestamp": datetime.now().isoformat()
    }
    
    ratings_data["ratings"].append(new_rating)
    save_ratings(ratings_data)
    
    return jsonify({"success": True, "rating_number": new_rating["n"]})

# Emotion detection and attention monitoring
emotion_detector = FER(mtcnn=True)
attention_status = "Not Paying Attention"
dominant_emotion = "neutral"

def is_paying_attention(emotions_dict, threshold=0.5):
    """Checks if the user is paying attention based on emotion scores."""
    dominant_emotion = max(emotions_dict, key=emotions_dict.get)
    emotion_score = emotions_dict[dominant_emotion]
    return emotion_score > threshold, dominant_emotion

def detect_emotion_and_attention(frame):
    """Detects emotion and attention from the frame."""
    global attention_status, dominant_emotion

    display_frame = cv2.flip(frame.copy(), 1)
    results = emotion_detector.detect_emotions(frame)

    for result in results:
        bounding_box = result["box"]
        emotions_dict = result["emotions"]

        paying_attention, dominant_emotion = is_paying_attention(emotions_dict)
        attention_status = "Paying Attention" if paying_attention else "Not Paying Attention"

        x, y, w, h = bounding_box
        flipped_x = display_frame.shape[1] - (x + w)

        cv2.rectangle(display_frame, (flipped_x, y), (flipped_x + w, y + h), (255, 0, 0), 2)
        
        emotion_text = ", ".join([f"{emotion}: {prob:.2f}" for emotion, prob in emotions_dict.items()])
        cv2.putText(display_frame, f"{dominant_emotion} ({attention_status})", 
                    (flipped_x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(display_frame, emotion_text, 
                    (flipped_x, y + h + 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    return display_frame

def generate_frames():
    """Captures frames from the webcam and detects emotion and attention."""
    cap = cv2.VideoCapture(0)
    
    while True:
        success, frame = cap.read()
        if not success:
            break

        processed_frame = detect_emotion_and_attention(frame)
        _, buffer = cv2.imencode('.jpg', processed_frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route('/talk_to_me', methods=['GET', 'POST'])
@login_required
def talk_to_me():
    """Handles the user's input and sends it to the chatbot along with emotion and attention."""
    global attention_status, dominant_emotion

    if request.method == 'GET':
        return render_template('talk_to_me.html')

    elif request.method == 'POST':
        user_input = request.form.get('user_input', '')

        prompt = f"The user is in a {dominant_emotion} mood and is {'paying attention' if attention_status == 'Paying Attention' else 'not paying attention'}."
        bot_response = gemma_chat(user_input + " " + prompt)

        return jsonify({'response': bot_response})

@app.route('/video_feed')
def video_feed():
    """Video feed for emotion detection."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Admin routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard."""
    if session.get('role') != 'admin':
        flash('Access restricted. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    users = load_users()
    current_admin = session['email']
    
    return render_template(
        'admin_dashboard.html',
        users=users,
        current_admin=current_admin,
        admin_since=get_admin_info(current_admin)
    )

def get_admin_info(admin_email):
    """Get admin creation info."""
    users = load_users()
    for user in users:
        if user['email'] == admin_email:
            return user.get('created_at', 'Unknown')
    return 'Unknown'

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    """Create new user (admin only)."""
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        users = load_users()
        
        if any(user['email'] == email for user in users):
            return render_template('create_user.html', error='Email already exists.')
        
        hashed_password = hash_password(password)
        username = email.split("@")[0]
        
        new_user = {
            'username': username,
            'name': name,
            'email': email,
            'password': hashed_password,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'created_by': session['email']
        }
        
        users.append(new_user)
        save_users(users)
            
        return redirect(url_for('admin_dashboard'))
        
    return render_template('create_user.html')

@app.route('/admin/update_role/<user_email>', methods=['POST'])
@login_required
def update_role(user_email):
    """Update user role (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    new_role = request.form.get('new_role')
    
    if not new_role or new_role not in ['user', 'admin', 'doctor']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    users = load_users()
    
    user_found = False
    for user in users:
        if user['email'] == user_email:
            user['role'] = new_role
            user['updated_at'] = datetime.now().isoformat()
            user['updated_by'] = session['email']
            user_found = True
            break
    
    if not user_found:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    save_users(users)
    
    return jsonify({'success': True, 'message': 'Role updated successfully'})

# Appointment system
AVAILABLE_SLOTS = [
    '10:00-11:00',
    '12:00-13:00',
    '15:00-16:00',
    '17:00-18:00'
]

def check_appointment_limits(username, appointment_date):
    """Check appointment booking limits."""
    appointments_file = f'{BASE_DIRS["appointments"]}/{username}.json'
    
    try:
        with open(appointments_file, 'r') as f:
            appointments = json.load(f)
    except FileNotFoundError:
        return True, None
        
    # Weekly limit check
    week_start = appointment_date - timedelta(days=appointment_date.weekday())
    week_end = week_start + timedelta(days=6)
    week_appointments = [a for a in appointments 
                        if week_start <= datetime.strptime(a['date'], '%Y-%m-%d').date() <= week_end
                        and a['status'] != 'cancelled']
    
    if len(week_appointments) >= 1:
        return False, "Weekly limit reached (maximum 1 appointment per week)"
        
    # Monthly limit check
    month_start = appointment_date.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    month_appointments = [a for a in appointments 
                         if month_start <= datetime.strptime(a['date'], '%Y-%m-%d').date() <= month_end
                         and a['status'] != 'cancelled']
    
    if len(month_appointments) >= 4:
        return False, "Monthly limit reached (maximum 4 appointments per month)"
        
    return True, None

def save_appointment(username, appointment_data):
    """Save appointment data."""
    file_path = f'{BASE_DIRS["appointments"]}/{username}.json'
    
    try:
        with open(file_path, 'r') as f:
            appointments = json.load(f)
    except FileNotFoundError:
        appointments = []
        
    appointments.append(appointment_data)
    
    with open(file_path, 'w') as f:
        json.dump(appointments, f, indent=4)

def get_user_basic_info(username):
    """Get basic user information."""
    try:
        with open(f'{BASE_DIRS["user_data"]}/{username}.json', 'r') as f:
            user_data = json.load(f)
        return user_data
    except FileNotFoundError:
        return {
            'age': 'Unknown',
            'gender': 'Unknown',
            'occupation': 'Unknown'
        }

def get_appointment_history(username):
    """Get user's appointment history."""
    try:
        with open(f'{BASE_DIRS["appointments"]}/{username}.json', 'r') as f:
            appointments = json.load(f)
        return appointments
    except FileNotFoundError:
        return []

def get_mood_history(username):
    """Get user's mood tracking history."""
    try:
        with open(f'{BASE_DIRS["mood_data"]}/{username}_moods.json', 'r') as f:
            moods = json.load(f)
        return moods
    except FileNotFoundError:
        return []

def get_questionnaire_responses(username):
    """Get user's questionnaire responses."""
    responses = {
        'close_ended': [],
        'open_ended': []
    }
    
    try:
        with open(f'{BASE_DIRS["responses_close"]}/{username}.csv', 'r') as f:
            reader = csv.DictReader(f)
            responses['close_ended'] = list(reader)
    except FileNotFoundError:
        pass
        
    try:
        with open(f'{BASE_DIRS["responses_open"]}/{username}.csv', 'r') as f:
            reader = csv.DictReader(f)
            responses['open_ended'] = list(reader)
    except FileNotFoundError:
        pass
        
    return responses

def send_appointment_confirmation(appointment_data, recipient_email=None):
    """Send appointment confirmation email."""
    username = appointment_data.get('patient')
    
    if not recipient_email:
        try:
            users = load_users()
            user = next((u for u in users if u.get('username') == username or u.get('name') == username), None)
            if user:
                recipient_email = user.get('email')
            else:
                app.logger.error(f"Could not find email for user: {username}")
                return False
        except Exception as e:
            app.logger.error(f"Error retrieving user email: {str(e)}")
            return False
    
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        app.logger.error("Email credentials not found in environment variables")
        return False
    
    appointment_date = appointment_data.get('date')
    appointment_slot = appointment_data.get('slot')
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = "Your Appointment Confirmation"
    
    body = f"""
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 20px;
        }}
        .email-container {{
            max-width: 600px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
            margin: auto;
        }}
        h2 {{
            color: #333;
            text-align: center;
        }}
        .appointment-details {{
            background: #eaf5ff;
            padding: 10px;
            border-left: 4px solid #007bff;
            margin: 15px 0;
        }}
        .join-button {{
            display: inline-block;
            background: #007bff;
            color: white;
            text-decoration: none;
            padding: 10px 15px;
            border-radius: 5px;
            font-weight: bold;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <h2>Appointment Confirmation</h2>
        <p>Dear <strong>{username}</strong>,</p>
        <p>Your appointment has been scheduled for:</p>
        <div class="appointment-details">
            <p><strong>Date:</strong> {appointment_date}</p>
            <p><strong>Time:</strong> {appointment_slot}</p>
        </div>
        <p>Click below to join your appointment:</p>
        <p><a href="https://meet.google.com/qeb-uemw-sag" class="join-button">Join Here</a></p>
        <p>Please arrive 10 minutes before your scheduled time.</p>
        <p>If you need to cancel or reschedule, please do so at least 24 hours in advance.</p>
        <p>Consult with a Doctor before making any decisions.</p>
        <p>Thank you!</p>
    </div>
</body>
</html>
"""
    
    msg.attach(MIMEText(body, 'html'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        app.logger.info(f"Appointment confirmation email sent to {recipient_email}")
        return True
    except Exception as e:
        app.logger.error(f"Failed to send email: {str(e)}")
        return False

@app.route('/appointment')
@login_required
def appointment():
    """Patient appointment booking page."""
    if session.get('role') == 'doctor':
        return redirect(url_for('doctor_dashboard'))
    return render_template('patient_dashboard.html')

@app.route('/doctor/dashboard')
@login_required
def doctor_dashboard():
    """Doctor dashboard."""
    if session.get('role') != 'doctor':
        return redirect(url_for('appointment'))
    return render_template('doctor_dashboard.html')

@app.route('/api/appointments', methods=['GET', 'POST'])
@login_required
def handle_appointments():
    """Handle appointment API requests."""
    username = session.get('username')
    appointments_file = f'{BASE_DIRS["appointments"]}/{username}.json'
    
    if request.method == 'GET':
        try:
            with open(appointments_file, 'r') as f:
                appointments = json.load(f)
            return jsonify(appointments)
        except FileNotFoundError:
            return jsonify([])
    
    elif request.method == 'POST':
        data = request.json
        appointment_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        # Check if it's weekend
        if appointment_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return jsonify({'error': 'No appointments on weekends'}), 400
        
        # Check appointment limits
        can_book, limit_message = check_appointment_limits(username, appointment_date)
        if not can_book:
            return jsonify({'error': limit_message}), 400
            
        try:
            with open(appointments_file, 'r') as f:
                appointments = json.load(f)
        except FileNotFoundError:
            appointments = []
            
        new_appointment = {
            'id': len(appointments) + 1,
            'patient': username,
            'date': data['date'],
            'slot': data['slot'],
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'cancellation_reason': None
        }
        
        save_appointment(username, new_appointment)
        
        return jsonify(new_appointment)

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    """Update appointment status (doctor only)."""
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 401
        
    appointments_dir = BASE_DIRS["appointments"]
    doctor_username = session.get('username')
    doctor_appointments_dir = BASE_DIRS["doctor_appointments"]
    doctor_file = f'{doctor_appointments_dir}/{doctor_username}.json'
    
    for filename in os.listdir(appointments_dir):
        if not filename.endswith('.json'):
            continue
            
        file_path = os.path.join(appointments_dir, filename)
        with open(file_path, 'r') as f:
            appointments = json.load(f)
            appointment = next((a for a in appointments if a['id'] == appointment_id), None)
            
            if not appointment:
                continue
                
            appointment['status'] = request.json['status']
            
            patient_username = filename[:-5]  # Remove .json extension
            patient_email = None
            
            try:
                users = load_users()
                user = next((u for u in users if u.get('username') == patient_username or u.get('name') == patient_username), None)
                if user:
                    patient_email = user.get('email')
                    appointment['patient_email'] = patient_email
            except Exception as e:
                print(f"Error retrieving user email: {str(e)}")
            
            with open(file_path, 'w') as f:
                json.dump(appointments, f, indent=4)
                
            try:
                with open(doctor_file, 'r') as f:
                    doctor_appointments = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                doctor_appointments = []
                
            patient_info = get_user_basic_info(patient_username)
            
            if patient_email:
                patient_info['email'] = patient_email
                
            new_doctor_appointment = {
                'appointment_id': appointment_id,
                'patient': patient_username,
                'patient_email': patient_email,
                'date': appointment['date'],
                'slot': appointment['slot'],
                'status': request.json['status'],
                'patient_info': patient_info,
                'updated_at': datetime.now().isoformat()
            }
            
            doctor_appointments.append(new_doctor_appointment)
            
            with open(doctor_file, 'w') as f:
                json.dump(doctor_appointments, f, indent=4)
                
            if request.json['status'] == 'confirmed':
                send_appointment_confirmation(appointment, patient_email)
                
            return jsonify({'success': True})
            
    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/api/appointments/cancel/<int:appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    """Cancel appointment."""
    username = session.get('username')
    appointments_file = f'{BASE_DIRS["appointments"]}/{username}.json'
    
    with open(appointments_file, 'r') as f:
        appointments = json.load(f)
    
    appointment = next((a for a in appointments if a['id'] == appointment_id), None)
    if appointment:
        appointment['status'] = 'cancelled'
        appointment['cancellation_reason'] = request.json.get('reason')
        
        with open(appointments_file, 'w') as f:
            json.dump(appointments, f, indent=4)
            
        return jsonify({'success': True})
    
    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/api/available-slots', methods=['GET'])
@login_required
def get_available_slots():
    """Get available appointment slots."""
    return jsonify(AVAILABLE_SLOTS)

@app.route('/api/doctor/patient-info/<username>', methods=['GET'])
@login_required
def get_patient_info(username):
    """Get patient information (doctor only)."""
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 401
        
    patient_info = {
        'basic_info': get_user_basic_info(username),
        'appointment_history': get_appointment_history(username),
        'mood_history': get_mood_history(username),
        'questionnaire_responses': get_questionnaire_responses(username)
    }
    
    return jsonify(patient_info)

@app.route('/logout')
def logout():
    """Handle user logout."""
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("login"))

@app.route('/session-info')
@login_required
def session_info():
    """Get session information for debugging."""
    session_data = dict(session)
    return jsonify(session_data)

if __name__ == "__main__":
    app.run(debug=True, port=5000)