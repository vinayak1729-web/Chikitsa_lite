from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response, flash, Blueprint, current_app,send_file
import json
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
from pathlib import Path
import bcrypt
from dotenv import load_dotenv
import requests
import csv
import pandas as pd
from datetime import datetime, timedelta
from functools import wraps
from flask_mail import Mail, Message
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pytz
import uuid
import statistics
from datetime import date
from werkzeug.utils import secure_filename
import base64
import hashlib
import secrets

# Assuming these modules are defined elsewhere as they were imported in the original code
from Create_modules.close_end_questionaire import get_random_close_questions
from Create_modules.open_end_questions import get_random_open_questions
from Create_modules.csv_extracter import csv_to_string
from Create_modules.trained_chikitsa import chatbot_response
from Create_modules.image_analysis import analyze_image
from Create_modules.prompt import Gemini_prompt_main, Gemini_Questionaire_prompt, image_prompt

load_dotenv()
app = Flask(__name__)
app.secret_key = 'secret_key'

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = 'image_analysis/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ollama API configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
SYSTEM_PROMPT = """
You are Chikitsa, an empathetic AI psychiatrist, providing mental health support using evidence-based coping strategies, behaving like a best friend, showing love, care, and secular Bhagavad Gita lessons (e.g., focus on the present, detachment from outcomes) tailored to users' emotional needs. Acknowledge feelings, assess concerns, suggest actionable techniques, and recommend professional help for severe symptoms. Use a warm, inclusive tone, avoid religious references, and encourage gradual progress. Format your responses in markdown for clear presentation.
Reply like a real human, in 1 line only like a real human, show emotions and all; if user is male act like female, if female then act like male.
"""

def allowed_file(filename):
    """
    Checks if the file has an allowed extension.
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Define users.json path
USERS_FILE = "instance/users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_users(users):
    os.makedirs('instance', exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        # Local storage
        os.makedirs('instance', exist_ok=True)
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'w') as f:
                json.dump([], f)

        users = load_users()

        if any(user['email'] == email or user['name'] == name for user in users):
            return render_template('register.html', error='Email or username already exists.')

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
        return redirect('/questionnaire')

    return render_template('register.html')

@app.route('/questionnaire', methods=['GET', 'POST'])
def questionnaire():
    if 'email' not in session:
        return redirect('/login')
        
    if request.method == 'POST':
        age = request.form.get('age')
        gender = request.form.get('gender')
        occupation_type = request.form.get('occupation_type')
        occupation_detail = request.form.get('occupation_detail')
        occupation = occupation_detail if occupation_type == 'Other' else occupation_type
        
        users = load_users()
        user = next((user for user in users if user['email'] == session['email']), None)
        
        if user:
            # Update local storage
            os.makedirs('instance/user_data', exist_ok=True)
            user_data = {
                'age': age,
                'gender': gender,
                'occupation': occupation,
                'timestamp': datetime.now().isoformat()
            }
            
            filename = f"instance/user_data/{user['name']}.json"
            with open(filename, 'w') as f:
                json.dump(user_data, f, indent=4)
                
            return redirect('/login')
            
    return render_template('questionnaire.html')

def generate_code_verifier():
    code_verifier = secrets.token_urlsafe(64)
    return code_verifier[:128]

def generate_code_challenge(code_verifier):
    code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8').rstrip('=')
    return code_challenge

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')

        if not identifier or not password:
            return render_template('login.html', error='Please provide all credentials')

        users = load_users()
        user = next((user for user in users if user['email'] == identifier or user['name'] == identifier), None)

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['username'] = user['name']
            session['email'] = user['email']
            session['role'] = user.get('role', 'user')

            if session['role'] == 'admin':
                return redirect('/admin/dashboard')
            elif session['role'] == 'doctor':
                return redirect('/doctor/dashboard')
            else:
                return redirect('/home') 

        return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')

@app.route('/session-info')
def session_info():
    session_data = dict(session)
    return jsonify(session_data)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/home')
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
    
    meditation_data = {
        'timestamp': datetime.now().isoformat(),
        'duration': request.json.get('duration', 300),
        'completed': request.json.get('completed', True)
    }
    
    meditation_file = f'instance/meditation_data/{username}_meditation.json'
    os.makedirs('instance/meditation_data', exist_ok=True)
    
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
    username = session.get('username')
    meditation_file = f'instance/meditation_data/{username}_meditation.json'
    
    try:
        with open(meditation_file, 'r') as f:
            meditation_history = json.load(f)
            
        total_minutes = sum(session['duration'] for session in meditation_history)
        total_sessions = len(meditation_history)
        
        return jsonify({
            'total_minutes': total_minutes,
            'total_sessions': total_sessions,
            'recent_sessions': meditation_history[-5:]
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
    username = session.get('username')
    user_data_path = f'instance/user_data/{username}.json'
    
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
    username = session.get('username')
    user_data_path = f'instance/user_data/{username}.json'
    
    updated_data = {
        "age": request.form.get('age'),
        "gender": request.form.get('gender'),
        "occupation": request.form.get('occupation'),
        "timestamp": datetime.now().isoformat()
    }
    
    os.makedirs('instance/user_data', exist_ok=True)
    with open(user_data_path, 'w') as f:
        json.dump(updated_data, f, indent=4)
    
    return redirect(url_for('personal_info'))

@app.route('/closed_ended')
def close_ended():
    random_questions = get_random_close_questions()
    return render_template('closed_ended.html', questions=random_questions)

@app.route('/submit_close_end', methods=['POST'])
def submit_close_ended():
    if request.method == 'POST':
        responses = []
        for question in request.form:
            answer = request.form[question]
            responses.append((question, answer))
        
        save_to_csv(responses)
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
    mood_file = f'instance/mood_data/{username}_moods.json'
    
    os.makedirs('instance/mood_data', exist_ok=True)
    
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
    username = session.get('username')
    mood_file = f'instance/mood_data/{username}_moods.json'
    
    try:
        with open(mood_file, 'r') as f:
            moods = json.load(f)
            moods.sort(key=lambda x: x['timestamp'])
            return jsonify({'moods': moods})
    except FileNotFoundError:
        return jsonify({'moods': []})

def save_to_csv(responses):
    user_email = session.get('email')
    if not user_email:
        return
    
    users = load_users()
    user = next((user for user in users if user['email'] == user_email), None)
    if not user:
        return
    
    username = user['name']
    
    os.makedirs('responses/close_ended', exist_ok=True)
    
    file_path = f'responses/close_ended/{username}.csv'
    
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Question', 'Answer'])
        for response in responses:
            writer.writerow(response)

@app.route('/open_ended', methods=['GET', 'POST'])
def submit_opended():
    if request.method == 'POST':
        responses = {key: value for key, value in request.form.items()}
        save_responses_to_csv(responses)
        return redirect(url_for('thank_you'))
    else:
        random_questions = get_random_open_questions()
        return render_template('open_ended.html', questions=random_questions)
    
def save_responses_to_csv(responses):
    user_email = session.get('email')
    if not user_email:
        return
    
    users = load_users()
    user = next((user for user in users if user['email'] == user_email), None)
    if not user:
        return
    
    username = user['name']
    
    os.makedirs('responses/open_ended', exist_ok=True)
    
    file_path = f'responses/open_ended/{username}.csv'
    
    data_to_save = [(question, responses[question]) for question in responses]
    
    df = pd.DataFrame(data_to_save, columns=['Question', 'Response'])
    
    df.to_csv(file_path, mode='w', index=False)

@app.route('/thank_you')
def thank_you():
    email = session.get('email')

    if email:
        users = load_users()
        user = next((user for user in users if user['email'] == email), None)
        if user:
            user_name = user['name']
            close_ended_str = csv_to_string(f"responses/close_ended/{user_name}.csv")
            open_ended_str = csv_to_string(f"responses/open_ended/{user_name}.csv")
        else:
            user_name = "Guest"
            close_ended_str = ""
            open_ended_str = ""
    else:
        user_name = "Guest"
        close_ended_str = ""
        open_ended_str = ""

    # Use Ollama instead of Gemini
    payload = {
        "model": "gemma3n:e2b",
        "prompt": Gemini_Questionaire_prompt() + " " + close_ended_str + " " + open_ended_str,
        "system": SYSTEM_PROMPT,
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        judge_gemini = response.json().get('response', 'Error processing response')
    except Exception as e:
        judge_gemini = f"Error: {str(e)}"
    
    return render_template('thank_you.html', judge_gemini=judge_gemini, user_name=user_name, completejudege=judge_gemini)

@app.route('/feedback')
def feedback():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session.get('username')
    user_file = f'instance/user_data/{username}.json'
    
    try:
        with open(user_file, 'r') as f:
            user_data = json.load(f)
            
        if 'wellness_report' in user_data:
            judge_gemini = user_data['wellness_report']
        else:
            close_ended_str = csv_to_string(f"responses/close_ended/{username}.csv")
            open_ended_str = csv_to_string(f"responses/open_ended/{username}.csv")
            
            default = "This is my assessment of close-ended questions and open-ended questions. Please provide feedback on me in friendly tone in summary like a professional psychiatrist."
            
            # Use Ollama instead of Gemini
            payload = {
                "model": "gemma3n:e2b",
                "prompt": default + " " + close_ended_str + " " + open_ended_str,
                "system": SYSTEM_PROMPT,
                "stream": False
            }
            
            try:
                response = requests.post(OLLAMA_API_URL, json=payload)
                response.raise_for_status()
                judge_gemini = response.json().get('response', 'Error processing response')
                
                user_data['wellness_report'] = judge_gemini
                with open(user_file, 'w') as f:
                    json.dump(user_data, f, indent=4)
            except Exception as e:
                judge_gemini = f"Error: {str(e)}"
    
    except FileNotFoundError:
        close_ended_str = csv_to_string(f"responses/close_ended/{username}.csv")
        open_ended_str = csv_to_string(f"responses/open_ended/{username}.csv")
        
        default = "This is my assessment of close-ended questions and open-ended questions. Please provide feedback on me in friendly tone in summary like a professional psychiatrist."
        
        # Use Ollama instead of Gemini
        payload = {
            "model": "gemma3n:e2b",
            "prompt": default + " " + close_ended_str + " " + open_ended_str,
            "system": SYSTEM_PROMPT,
            "stream": False
        }
        
        try:
            response = requests.post(OLLAMA_API_URL, json=payload)
            response.raise_for_status()
            judge_gemini = response.json().get('response', 'Error processing response')
            
            user_data = {
                "age": "",
                "gender": "",
                "occupation": "",
                "timestamp": datetime.now().isoformat(),
                "wellness_report": judge_gemini
            }
            
            os.makedirs('instance/user_data', exist_ok=True)
            with open(user_file, 'w') as f:
                json.dump(user_data, f, indent=4)
        except Exception as e:
            judge_gemini = f"Error: {str(e)}"
    
    return render_template('thank_you.html', 
                         judge_gemini=judge_gemini, 
                         user_name=username, 
                         completejudege=judge_gemini)

@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect('/login')

@app.route('/send_message')
def send_message():
    """Stream AI response for user messages."""
    if "username" not in session:
        return Response("data: {'text': 'Please log in'}\n\n", content_type='text/event-stream')
    message = request.args.get("message", "").strip()
    if not message:
        return Response("data: {'text': 'No message provided'}\n\n", content_type='text/event-stream')

    payload = {"model": "gemma3n:e2b", "prompt": message, "system": SYSTEM_PROMPT, "stream": True}

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

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'GET':
        return render_template('chat.html')
    elif request.method == 'POST':
        try:
            data = request.get_json()
            user_input = data.get('message')
            
            # Use Ollama instead of Gemini
            payload = {
                "model": "gemma3n:e2b",
                "prompt": user_input,
                "system": SYSTEM_PROMPT,
                "stream": False
            }
            
            response = requests.post(OLLAMA_API_URL, json=payload)
            response.raise_for_status()
            bot_response = response.json().get('response', 'Error processing response')
            
            # Log conversation
            log_conversation(user_input, bot_response)
            
            return jsonify({'response': bot_response})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/image_analysis', methods=['GET', 'POST'])
def image_analysis():
    analysis = None
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)

        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return redirect(request.url)

        if uploaded_file and allowed_file(uploaded_file.filename):
            # Save the file temporarily
            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            uploaded_file.save(file_path)
            
            # Read image data
            with open(file_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Prepare payload for Ollama
            payload = {
                "model": "gemma3n:e2b",
                "prompt": image_prompt,
                "system": SYSTEM_PROMPT,
                "images": [image_data],
                "stream": False
            }
            
            try:
                response = requests.post(OLLAMA_API_URL, json=payload)
                response.raise_for_status()
                analysis = response.json().get('response', 'Error processing image')
            except Exception as e:
                analysis = f"Error: {str(e)}"
            
            # Clean up
            os.remove(file_path)
    
    return render_template('image_analysis.html', analysis=analysis)

RATINGS_FILE = Path('instance/rating/ratings.json')

def load_ratings():
    if RATINGS_FILE.exists():
        with open(RATINGS_FILE, 'r') as f:
            return json.load(f)
    return {"ratings": []}

def save_ratings(ratings_data):
    RATINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RATINGS_FILE, 'w') as f:
        json.dump(ratings_data, f, indent=4)

@app.route('/save_rating', methods=['POST'])
def save_rating():
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

@app.route('/talk_to_me', methods=['GET', 'POST'])
def talk_to_me():
    attention_status = "Unknown"
    dominant_emotion = "Unknown"

    if request.method == 'GET':
        return render_template('talk_to_me.html')

    elif request.method == 'POST':
        user_input = request.form.get('user_input', '')

        prompt = f"The user is in a {dominant_emotion} mood and is {'paying attention' if attention_status == 'Paying Attention' else 'not paying attention'}."

        # Use Ollama instead of Gemini
        payload = {
            "model": "gemma3n:e2b",
            "prompt": user_input + " " + prompt,
            "system": SYSTEM_PROMPT,
            "stream": False
        }
        
        try:
            response = requests.post(OLLAMA_API_URL, json=payload)
            response.raise_for_status()
            bot_response = response.json().get('response', 'Error processing response')
            
            log_conversation(user_input, bot_response)
            
            return jsonify({'response': bot_response})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

def log_conversation(user_input, bot_response, history_file="dataset/intents.json"):
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            intents_data = json.load(f)
    else:
        intents_data = {"intents": []}

    new_intent = {
        "patterns": [user_input],
        "responses": [bot_response],
    }

    intents_data['intents'].append(new_intent)

    with open(history_file, 'w') as f:
        json.dump(intents_data, f, indent=4)
import os
import json
from datetime import datetime, date, timedelta
from flask import render_template, redirect, url_for, flash, session, jsonify, request, send_file
from werkzeug.utils import secure_filename

# Global variables for recording
recording = False
out = None
cap = None

BASE_DIRS = {
    "game_userdata": "instance/game/user_data",
    "game_video": "instance/game/video",
    "game_audio": "instance/game/audio"
}

def ensure_directories():
    """Ensure all game directories exist."""
    for dir_path in BASE_DIRS.values():
        os.makedirs(dir_path, exist_ok=True)

def has_played_today(username):
    """Check if user has played today."""
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    if os.path.exists(game_file):
        with open(game_file, 'r') as f:
            game_data = json.load(f)
            today = date.today().isoformat()
            return any(session["date"] == today for session in [s for sessions in game_data.values() for s in sessions])
    return False

def record_video(username, duration):
    """Record video (placeholder function, to be implemented with actual recording logic)."""
    filename = os.path.join(BASE_DIRS["game_video"], f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
    # Add actual video recording logic here using OpenCV or similar
    return filename

def save_recording(username, file, file_type):
    """Save uploaded recording file."""
    if file_type == "video":
        directory = BASE_DIRS["game_video"]
    elif file_type == "audio":
        directory = BASE_DIRS["game_audio"]
    else:
        return None
        
    filename = secure_filename(f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file.filename.rsplit('.', 1)[1]}")
    file_path = os.path.join(directory, filename)
    file.save(file_path)
    return file_path

def save_game_results(username, data):
    """Save game results to JSON."""
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    try:
        if os.path.exists(game_file):
            with open(game_file, 'r') as f:
                game_data = json.load(f)
        else:
            game_data = {}
        
        today = date.today().isoformat()
        game_data[today] = data
        with open(game_file, 'w') as f:
            json.dump(game_data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving game results: {e}")
        return False

def log_game_session(username):
    """Log game session in user log."""
    log_file = os.path.join("instance", "user_log.json")
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                log_data = json.load(f)
        else:
            log_data = {}
        
        log_data[username] = log_data.get(username, []) + [{
            "date": date.today().isoformat(),
            "login_time": datetime.now().isoformat(),
            "game_time": datetime.now().isoformat(),
            "game_played": True
        }]
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=4)
    except Exception as e:
        print(f"Error logging game session: {e}")

def analyze_performance(username):
    """Analyze user game performance."""
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    if not os.path.exists(game_file):
        return {"message": "No game data available"}
    with open(game_file, 'r') as f:
        game_data = json.load(f)
        all_sessions = [session for sessions in game_data.values() for session in sessions]
        if not all_sessions:
            return {"message": "No game data available"}
        return {"sessions": len(all_sessions)}  # Extend with detailed analysis as needed

def generate_pdf_report(username, analysis):
    """Generate PDF report (placeholder function)."""
    # Implement PDF generation logic here
    from io import BytesIO
    pdf_buffer = BytesIO()
    # Placeholder for PDF content
    return pdf_buffer

@app.route("/game")
def game():
    """Main game route with authentication."""
    if "username" not in session:
        flash("Please log in to access the game", "error")
        return redirect(url_for("login"))
    if has_played_today(session["username"]):
        flash("You have already played the game today. Come back tomorrow!", "info")
        return redirect(url_for("home"))
    return render_template("game.html")

@app.route("/video_feed")
def video_feed():
    """Stream video feed for game recording."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/start_recording", methods=["POST"])
def start_recording():
    """Start video recording for the game."""
    global recording
    if "username" not in session:
        return jsonify({"status": "Not logged in"})
    if not recording:
        duration = int(request.form.get("duration", 10))  # Default 10 seconds
        recording = True
        video_filename = record_video(session["username"], duration)
        return jsonify({"status": "Recording started", "duration": duration, "video_filename": video_filename})
    return jsonify({"status": "Already recording"})

@app.route("/stop_recording", methods=["POST"])
def stop_recording():
    """Stop video recording for the game."""
    global recording, out, cap
    recording = False
    if out is not None:
        out.release()
    if cap is not None:
        cap.release()
    return jsonify({"status": "Recording stopped"})

@app.route("/game/submit", methods=["POST"])
def submit_game_results():
    """Submit game results and recordings."""
    global recording, out, cap
    if "username" not in session:
        return jsonify({"success": False, "message": "Not logged in"})
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
def game_analysis():
    """Show game analysis with authentication."""
    if "username" not in session:
        flash("Please log in to view analysis", "error")
        return redirect(url_for("login"))
    analysis = analyze_performance(session["username"])
    return render_template("game_analysis.html", analysis=analysis, username=session["username"])

@app.route("/game/download-report")
def download_report():
    """Download PDF report with authentication."""
    if "username" not in session:
        flash("Please log in to download report", "error")
        return redirect(url_for("login"))
    username = session["username"]
    analysis = analyze_performance(username)
    if "message" in analysis and "No game data" in analysis["message"]:
        flash("No game data available for report generation", "error")
        return redirect(url_or("game_analysis"))
    pdf_buffer = generate_pdf_report(username, analysis)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{username}_tap_impulse_analysis_{date.today().isoformat()}.pdf",
        mimetype="application/pdf"
    )

@app.route("/api/game/data")
def get_game_data():
    """API endpoint to get game data with authentication."""
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{session['username']}_game_tap_impulse.json")
    return jsonify(read_json_file(game_file))

def read_json_file(file_path):
    """Read JSON file with error handling."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error reading JSON file {file_path}: {e}")
        return {}

# Ensure directories are created when the app starts
ensure_directories()

@app.route("/profile")
def profile():
    if "username" not in session:
        flash("Please log in to view your profile", "error")
        return redirect(url_for("login"))
    
    username = session["username"]
    
    log_file = os.path.join("instance", "user_log.json")
    log_data = read_json_file(log_file).get(username, [])
    
    login_count = len(log_data)
    game_played_count = sum(1 for log in log_data if log.get("game_played", False))
    last_30_days = (date.today() - timedelta(days=30)).isoformat()
    recent_logins = sum(1 for log in log_data if log.get("date") >= last_30_days)
    recent_games = sum(1 for log in log_data if log.get("date") >= last_30_days and log.get("game_played", False))
    
    traction_data = {
        "total_logins": login_count,
        "total_games_played": game_played_count,
        "recent_logins_30d": recent_logins,
        "recent_games_30d": recent_games,
        "last_login": max((log.get("login_time") for log in log_data), default="N/A"),
        "last_game": max((log.get("game_time") for log in log_data if log.get("game_time")), default="N/A")
    }
    
    wellness_data = load_wellness_data(username)
    close_ended = wellness_data.get("questionnaire", {}).get("close_ended", [])
    open_ended = wellness_data.get("questionnaire", {}).get("open_ended", [])
    wellness_report = wellness_data.get("wellness_report", "No wellness report available.")
    
    positive_count = sum(1 for resp in close_ended if "positive" in resp.get("answer", "").lower())
    negative_count = sum(1 for resp in close_ended if "negative" in resp.get("answer", "").lower())
    mental_state_summary = {
        "close_ended_responses": len(close_ended),
        "open_ended_responses": len(open_ended),
        "positive_responses": positive_count,
        "negative_responses": negative_count,
        "wellness_report_snippet": wellness_report[:200] + "..." if len(wellness_report) > 200 else wellness_report
    }
    
    game_file = os.path.join(BASE_DIRS["game_userdata"], f"{username}_game_tap_impulse.json")
    game_data = read_json_file(game_file)
    all_sessions = [session for sessions in game_data.values() for session in sessions]
    
    if not all_sessions:
        flash("No game data available", "error")
        return render_template(
            "profile.html",
            username=username,
            traction=traction_data,
            mental_state=mental_state_summary,
            game_performance={"message": "No game data available"},
            mental_health_indicators={},
            chart_data={}
        )
    
    game_session = all_sessions[0]
    detailed_responses = game_session.get("detailed_responses", [])
    total_responses = len(detailed_responses)
    correct_responses = game_session.get("correct_responses", 0)
    incorrect_responses = game_session.get("incorrect_responses", 0)
    reaction_times = [resp.get("reaction_time", 0) for resp in detailed_responses]
    avg_reaction_time = sum(reaction_times) / total_responses if total_responses else 0
    fastest_reaction_time = min(reaction_times) if reaction_times else 0
    slowest_reaction_time = max(reaction_times) if reaction_times else 0
    accuracy_rate = (correct_responses / total_responses * 100) if total_responses else 0
    
    consistency = "Mixed"
    if detailed_responses:
        purple_responses = [r for r in detailed_responses if r["word"] == "Purple"]
        if all(r["correct"] for r in purple_responses) or all(not r["correct"] for r in purple_responses):
            consistency = "Consistent"
        else:
            consistency = "Mixed (Correct → Incorrect alternation)"
    
    correct_rt = [r["reaction_time"] for r in detailed_responses if r["correct"]]
    incorrect_rt = [r["reaction_time"] for r in detailed_responses if not r["correct"]]
    avg_correct_rt = sum(correct_rt) / len(correct_rt) if correct_rt else 0
    avg_incorrect_rt = sum(incorrect_rt) / len(incorrect_rt) if incorrect_rt else 0
    total_time = game_session.get("total_time", 0)
    mfs = ((avg_incorrect_rt - avg_correct_rt) / total_time * 100) if total_time and avg_incorrect_rt > avg_correct_rt else 0
    
    consistency_score = statistics.stdev(reaction_times) if len(reaction_times) > 1 else 0
    
    mental_health_indicators = {
        "total_responses": total_responses,
        "correct_responses": correct_responses,
        "incorrect_responses": incorrect_responses,
        "avg_reaction_time": round(avg_reaction_time / 1000, 2),
        "fastest_reaction_time": round(fastest_reaction_time / 1000, 2),
        "slowest_reaction_time": round(slowest_reaction_time / 1000, 2),
        "accuracy_rate": round(accuracy_rate, 2),
        "cognitive_control_consistency": consistency,
        "mental_fatigue_score": round(mfs, 2),
        "consistency_score": round(consistency_score, 2)
    }
    
    recommendations = []
    if mfs > 25:
        recommendations.append("May be experiencing cognitive overload. Recommend mindfulness or reduced screen time.")
    if accuracy_rate < 70:
        recommendations.append("Attention may be impaired. Suggest sleep or break.")
    if consistency_score > 1000:
        recommendations.append("High variability in reaction times suggests mental strain or lack of focus.")
    
    chart_data = {
        "cognitive_performance": {
            "labels": [f"Response {i+1}" for i in range(total_responses)],
            "reaction_times": [r["reaction_time"] / 1000 for r in detailed_responses],
            "correctness": ["green" if r["correct"] else "red" for r in detailed_responses]
        },
        "accuracy_heatmap": {
            "labels": sorted(set(r["word"] + "-" + r["color"] for r in detailed_responses)),
            "data": [
                sum(1 for r in detailed_responses if r["word"] + "-" + r["color"] == label and r["correct"])
                for label in sorted(set(r["word"] + "-" + r["color"] for r in detailed_responses))
            ]
        },
        "attention_drift": {
            "labels": [f"Response {i+1}" for i in range(total_responses)],
            "reaction_times": [r["reaction_time"] / 1000 for r in detailed_responses],
            "correctness": [1 if r["correct"] else 0 for r in detailed_responses]
        }
    }
    
    return render_template(
        "profile.html",
        username=username,
        traction=traction_data,
        mental_state=mental_state_summary,
        game_performance=mental_health_indicators,
        mental_health_indicators=mental_health_indicators,
        recommendations=recommendations,
        chart_data=chart_data
    )

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'email' not in session:
        flash('Please login first', 'warning')
        return redirect('/login')
    
    if session.get('role') != 'admin':
        flash('Access restricted. Admin privileges required.', 'error')
        return redirect('/')
    
    users = load_users()
    current_admin = session['email']
    
    return render_template(
        'admin_dashboard.html',
        users=users,
        current_admin=current_admin,
        admin_since=get_admin_info(current_admin)
    )

def get_admin_info(admin_email):
    users = load_users()
    for user in users:
        if user['email'] == admin_email:
            return user.get('created_at', 'Unknown')
    return 'Unknown'

@app.route('/admin/create_user', methods=['GET', 'POST'])
def create_user():
    if 'email' not in session or session.get('role') != 'admin':
        return redirect('/login')
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        users = load_users()
        
        if any(user['email'] == email for user in users):
            return render_template('create_user.html', error='Email already exists.')
        
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
            
        return redirect('/admin/dashboard')
        
    return render_template('create_user.html')

@app.route('/admin/update_role/<user_email>', methods=['POST'])
def update_role(user_email):
    if 'email' not in session or session.get('role') != 'admin':
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
    appointments_file = f'instance/appointments/{username}.json'
    os.makedirs('instance/appointments', exist_ok=True)
    
    if request.method == 'GET':
        try:
            with open(appointments_file, 'r') as f:
                appointments = json.load(f)
            return jsonify(appointments)
        except FileNotFoundError:
            return jsonify([])
    
    elif request.method == 'POST':
        data = request.json
        appointment_date = datetime.strptime(data['date'], '%Y-%m-%d')
        
        if appointment_date.weekday() >= 5:
            return jsonify({'error': 'No appointments on weekends'}), 400
        
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
            'cancellation_reason': None,
            'meet_link': 'https://meet.google.com/qhe-nfdr-wvs'  # Random Google Meet link
        }
        
        save_appointment(username, new_appointment)
        
        update_appointment_stats(username, 'booked', appointment_date)
        
        return jsonify(new_appointment)

def update_appointment_stats(username, action, date):
    stats_file = f'instance/appointment_stats/{username}.json'
    os.makedirs('instance/appointment_stats', exist_ok=True)
    
    try:
        with open(stats_file, 'r') as f:
            stats = json.load(f)
    except FileNotFoundError:
        stats = {
            'total_appointments': 0,
            'total_cancellations': 0,
            'yearly_stats': {},
            'monthly_stats': {},
            'rating': 'white'
        }
    
    year = str(date.year)
    month = str(date.month)
    
    if year not in stats['yearly_stats']:
        stats['yearly_stats'][year] = {'booked': 0, 'cancelled': 0}
    if month not in stats['monthly_stats']:
        stats['monthly_stats'][month] = {'booked': 0, 'cancelled': 0}
        
    if action == 'booked':
        stats['total_appointments'] += 1
        stats['yearly_stats'][year]['booked'] += 1
        stats['monthly_stats'][month]['booked'] += 1
    elif action == 'cancelled':
        stats['total_cancellations'] += 1
        stats['yearly_stats'][year]['cancelled'] += 1
        stats['monthly_stats'][month]['cancelled'] += 1
        
    monthly_cancel_rate = stats['monthly_stats'][month]['cancelled'] / max(stats['monthly_stats'][month]['booked'], 1)
    
    if monthly_cancel_rate < 0.1:
        stats['rating'] = 'blue'
    elif monthly_cancel_rate > 0.4:
        stats['rating'] = 'red'
    else:
        stats['rating'] = 'white'
        
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=4)

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_appointment(appointment_id):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 401
        
    appointments_dir = 'instance/appointments'
    doctor_username = session.get('username')
    doctor_appointments_dir = 'instance/doctor_appointments'
    doctor_file = f'{doctor_appointments_dir}/{doctor_username}.json'
    
    os.makedirs(doctor_appointments_dir, exist_ok=True)
    
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
            
            patient_username = filename[:-5]
            patient_email = None
            
            try:
                with open('instance/users.json', 'r') as users_file:
                    users = json.load(users_file)
                    user = next((u for u in users if u.get('name') == patient_username), None)
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
                'updated_at': datetime.now().isoformat(),
                'meet_link': 'https://meet.google.com/qhe-nfdr-wvs'  # Random Google Meet link
            }
            
            doctor_appointments.append(new_doctor_appointment)
            
            with open(doctor_file, 'w') as f:
                json.dump(doctor_appointments, f, indent=4)
                
            if request.json['status'] == 'confirmed':
                send_appointment_confirmation(appointment, patient_email)
                
            return jsonify({'success': True})
            
    return jsonify({'error': 'Appointment not found'}), 404

def get_user_appointment_stats(username):
    stats_file = f'instance/appointment_stats/{username}.json'
    os.makedirs('instance/appointment_stats', exist_ok=True)
    
    try:
        with open(stats_file, 'r') as f:
            stats = json.load(f)
    except FileNotFoundError:
        stats = {
            'total_appointments': 0,
            'total_cancellations': 0,
            'yearly_stats': {},
            'monthly_stats': {},
            'rating': 'white'
        }
    
    return stats

def calculate_patient_rating(username):
    stats = get_user_appointment_stats(username)
    monthly_appointments = stats['monthly_stats'].get(str(datetime.now().month), {})
    
    if not monthly_appointments:
        return 'white'
        
    total = monthly_appointments.get('booked', 0)
    cancelled = monthly_appointments.get('cancelled', 0)
    
    if total == 0:
        return 'white'
        
    cancel_rate = cancelled / total
    
    if cancel_rate < 0.1:
        return 'blue'
    elif cancel_rate > 0.4:
        return 'red'
    return 'white'

@app.route('/api/appointments/cancel/<int:appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    username = session.get('username')
    appointments_file = f'instance/appointments/{username}.json'
    
    with open(appointments_file, 'r') as f:
        appointments = json.load(f)
    
    appointment = next((a for a in appointments if a['id'] == appointment_id), None)
    if appointment:
        appointment['status'] = 'cancelled'
        appointment['cancellation_reason'] = request.json.get('reason')
        
        appointment_date = datetime.strptime(appointment['date'], '%Y-%m-%d')
        update_appointment_stats(username, 'cancelled', appointment_date)
        
        with open(appointments_file, 'w') as f:
            json.dump(appointments, f, indent=4)
            
        return jsonify({'success': True})
    
    return jsonify({'error': 'Appointment not found'}), 404

@app.route('/api/user/stats', methods=['GET'])
@login_required
def get_user_stats():
    username = session.get('username')
    return jsonify(get_user_appointment_stats(username))

AVAILABLE_SLOTS = [
    '10:00-11:00',
    '12:00-13:00',
    '15:00-16:00',
    '17:00-18:00'
]

@app.route('/api/available-slots', methods=['GET'])
@login_required
def get_available_slots():
    return jsonify(AVAILABLE_SLOTS)

@app.route('/api/doctor/patient-info/<username>', methods=['GET'])
@login_required
def get_patient_info(username):
    if session.get('role') != 'doctor':
        return jsonify({'error': 'Unauthorized'}), 401
        
    patient_info = {
        'basic_info': get_user_basic_info(username),
        'appointment_history': get_appointment_history(username),
        'mood_history': get_mood_history(username),
        'questionnaire_responses': get_questionnaire_responses(username)
    }
    
    return jsonify(patient_info)

def check_appointment_limits(username, appointment_date):
    appointments_file = f'instance/appointments/{username}.json'
    
    try:
        with open(appointments_file, 'r') as f:
            appointments = json.load(f)
    except FileNotFoundError:
        return True, None
        
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

def save_appointment(username, appointment_data):
    os.makedirs('instance/appointments', exist_ok=True)
    file_path = f'instance/appointments/{username}.json'
    
    try:
        with open(file_path, 'r') as f:
            appointments = json.load(f)
    except FileNotFoundError:
        appointments = []
        
    appointments.append(appointment_data)
    
    with open(file_path, 'w') as f:
        json.dump(appointments, f, indent=4)
    
    send_appointment_confirmation(appointment_data, appointment_data.get('patient_email'))

def get_user_basic_info(username):
    try:
        with open(f'instance/user_data/{username}.json', 'r') as f:
            user_data = json.load(f)
        return user_data
    except FileNotFoundError:
        return {
            'age': 'Unknown',
            'gender': 'Unknown',
            'occupation': 'Unknown'
        }

def get_appointment_history(username):
    try:
        with open(f'instance/appointments/{username}.json', 'r') as f:
            appointments = json.load(f)
        return appointments
    except FileNotFoundError:
        return []

def get_mood_history(username):
    try:
        with open(f'instance/mood_data/{username}_moods.json', 'r') as f:
            moods = json.load(f)
        return moods
    except FileNotFoundError:
        return []

def get_questionnaire_responses(username):
    responses = {
        'close_ended': [],
        'open_ended': []
    }
    
    try:
        with open(f'responses/close_ended/{username}.csv', 'r') as f:
            reader = csv.DictReader(f)
            responses['close_ended'] = list(reader)
    except FileNotFoundError:
        pass
        
    try:
        with open(f'responses/open_ended/{username}.csv', 'r') as f:
            reader = csv.DictReader(f)
            responses['open_ended'] = list(reader)
    except FileNotFoundError:
        pass
        
    return responses

def send_appointment_confirmation(appointment_data, recipient_email=None):
    username = appointment_data.get('patient')
    
    if not recipient_email:
        try:
            with open('instance/users.json', 'r') as f:
                users = json.load(f)
                user = next((u for u in users if u.get('name') == username), None)
                if user:
                    recipient_email = user.get('email')
                else:
                    current_app.logger.error(f"Could not find email for user: {username}")
                    return False
        except Exception as e:
            current_app.logger.error(f"Error retrieving user email: {str(e)}")
            return False
    
    sender_email = os.environ.get('EMAIL_USER')
    sender_password = os.environ.get('EMAIL_PASS')
    
    if not sender_email or not sender_password:
        current_app.logger.error("Email credentials not found in environment variables")
        return False
    
    appointment_date = appointment_data.get('date')
    appointment_slot = appointment_data.get('slot')
    meet_link = appointment_data.get('meet_link', 'https://meet.google.com/qhe-nfdr-wvs')
    
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
        p {{
            font-size: 16px;
            color: #555;
            line-height: 1.5;
        }}
        .appointment-details {{
            background: #eaf5ff;
            padding: 10px;
            border-left: 4px solid #007bff;
            margin: 15px 0;
        }}
        .appointment-details strong {{
            color: #007bff;
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
        .join-button:hover {{
            background: #0056b3;
        }}
        .footer {{
            font-size: 14px;
            color: #777;
            margin-top: 20px;
            text-align: center;
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
            <p><strong>Join Link:</strong> <a href="{meet_link}">{meet_link}</a></p>
        </div>
        <p>Click below to join your appointment:</p>
        <p><a href="{meet_link}" class="join-button">Join Here</a></p>
        <p>Please arrive 10 minutes before your scheduled time.</p>
        <p>If you need to cancel or reschedule, please do so at least 24 hours in advance.</p>
        <p class="footer">Thank you!</p>
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
        current_app.logger.info(f"Appointment confirmation email sent to {recipient_email}")
        
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email: {str(e)}")
        return False

if __name__ == "__main__":
    app.run(debug=True)
