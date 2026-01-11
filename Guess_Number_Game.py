import blackfire
blackfire.patch_all()

from flask import Flask, render_template, request, session, jsonify
from werkzeug.exceptions import HTTPException
import random, os, time, re, base64
from dotenv import load_dotenv
from supabase import create_client, Client
from functools import wraps
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-secret-key-change-me')

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if url and key:
    supabase: Client = create_client(url, key)
else:
    print("WARNING: Supabase URL/KEY missing. Database features will fail.")
    supabase = None

def get_cipher():
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'static_salt_for_game_logic',
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(app.secret_key.encode()))
    return Fernet(key)

cipher_suite = get_cipher()

DIFFICULTY_SETTINGS = {
    'easy':       {'max_number': 10,        'max_attempts': 3,  'points': 3},
    'medium':     {'max_number': 100,       'max_attempts': 8,  'points': 10},
    'hard':       {'max_number': 1000,      'max_attempts': 15, 'points': 20},
    'impossible': {'max_number': 100000,    'max_attempts': 25, 'points': 45},
    'million':    {'max_number': 1000000,   'max_attempts': 50, 'points': 150},
}

TITLES = [
    ("Newbie", 100), ("Rookie", 500), ("Pro", 2500), 
    ("Legend", 5000), ("Champion", 10000)
]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('username'):
            return jsonify({'error': 'Unauthorized', 'message': 'Please login first.'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return jsonify(error=e.name, message=e.description), e.code
    print(f"Server Error: {e}")
    return jsonify(error="Internal Server Error", message="Something went wrong."), 500

def save_score(username, points_to_add, won=False):
    if not supabase: return
    try:
        response = supabase.table('leaderboard').select('*').eq('username', username).execute()
        current_data = response.data[0] if response.data else {'points': 0, 'correct_guesses': 0, 'total_games': 0}

        new_total = current_data['total_games'] + 1
        new_points = current_data['points'] + points_to_add
        new_correct = current_data['correct_guesses'] + (1 if won else 0)

        supabase.table('leaderboard').upsert({
            'username': username, 'points': new_points,
            'correct_guesses': new_correct, 'total_games': new_total
        }).execute()
        
        session['points'] = new_points
        session['total_games'] = new_total
        session['correct_guesses'] = new_correct
    except Exception as e:
        print(f"Error saving score: {e}")

def get_title(points):
    for title, threshold in reversed(TITLES):
        if points >= threshold: return title
    return None

def check_if_the_one(username, points):
    if not supabase: return False
    try:
        response = supabase.table('leaderboard').select('username').order('points', desc=True).limit(1).execute()
        if response.data and response.data[0]['username'] == username:
            return True
    except: pass
    return False

def init_session_defaults():
    defaults = {
        'points': 0, 'total_games': 0, 'correct_guesses': 0,
        'difficulty': 'easy', 'attempts': 0, 'game_ready': False,
        'guess_history': [], 'is_the_one': False
    }
    for k, v in defaults.items():
        session.setdefault(k, v)

def clear_game_state():
    session.pop('target_token', None)
    session.pop('game_start_time', None)
    session['game_ready'] = False
    session['attempts'] = 0

@app.route('/')
def index():
    if session.get('game_ready'):
         clear_game_state()
         
    init_session_defaults()
    user_title = None
    if session.get('username'):
        pts = session.get('points', 0)
        user_title = get_title(pts)
        if session.get('is_the_one'): user_title = "THE ONE"

    return render_template('index.html', 
                           username=session.get('username'), 
                           user_title=user_title,
                           titles=TITLES)

@app.route('/api/login', methods=['POST'])
def login():
    if not request.is_json: return jsonify({'error': 'Invalid Content-Type'}), 400
    data = request.get_json()
    username = str(data.get('username', '')).strip()[:12]
    
    if not username or not re.match("^[a-zA-Z0-9]+$", username):
        return jsonify({'message': 'Invalid username.'}), 400
    
    session['username'] = username
    current_title = None
    
    if supabase:
        try:
            response = supabase.table('leaderboard').select('*').eq('username', username).execute()
            if response.data:
                user = response.data[0]
                session['points'] = user.get('points', 0)
                session['total_games'] = user.get('total_games', 0)
                session['correct_guesses'] = user.get('correct_guesses', 0)
                current_title = get_title(session['points'])
                if check_if_the_one(username, session['points']):
                    session['is_the_one'] = True
                    current_title = "THE ONE"
                else:
                    session['is_the_one'] = False
        except Exception as e:
            print(f"DB Error: {e}")

    return jsonify({'success': True, 'points': session.get('points', 0), 'title': current_title})

@app.route('/api/difficulty', methods=['POST'])
@login_required
def set_difficulty():
    clear_game_state()
    data = request.get_json(silent=True) or {}
    new_diff = data.get('difficulty', 'easy')
    if new_diff not in DIFFICULTY_SETTINGS:
        return jsonify({'message': 'Invalid difficulty'}), 400

    session['difficulty'] = new_diff
    return jsonify({
        'message': f"Difficulty set to {session['difficulty'].capitalize()}.",
        'max_number': DIFFICULTY_SETTINGS[session['difficulty']]['max_number']
    })

@app.route('/api/start', methods=['POST'])
@login_required
def start_game():
    clear_game_state()
    settings = DIFFICULTY_SETTINGS[session.get('difficulty', 'easy')]
    target_number = random.randint(1, settings['max_number'])
    
    encrypted_target = cipher_suite.encrypt(str(target_number).encode()).decode()
    session['target_token'] = encrypted_target
    
    session['attempts'] = 0
    session['game_ready'] = True
    session['game_start_time'] = time.time()
    session['guess_history'] = []
    
    return jsonify({
        'message': "Game Started!",
        'game_ready': True,
        'max_number': settings['max_number']
    })

@app.route('/api/guess', methods=['POST'])
@login_required
def guess():
    if not session.get('game_ready') or 'target_token' not in session:
        return jsonify({'error': 'State Error', 'message': 'Game not started'}), 400

    current_time = time.time()
    last_guess = session.get('last_guess_time', 0)
    if current_time - last_guess < 0.3:
        return jsonify({'status': 'warning', 'message': "⚠️ Slow down! Too fast."})
    session['last_guess_time'] = current_time

    data = request.get_json(silent=True)
    try:
        guess_val = int(data.get('guess'))
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': "⚠️ Invalid number."}), 400

    try:
        target_token = session['target_token']
        correct_num = int(cipher_suite.decrypt(target_token.encode()).decode())
    except Exception as e:
        print(f"Decryption failed: {e}")
        return jsonify({'error': 'Security Error', 'message': 'Session invalid. Restart game.'}), 400

    settings = DIFFICULTY_SETTINGS[session['difficulty']]
    
    history = session.get('guess_history', [])
    history.append(guess_val)
    session['guess_history'] = history
    
    if guess_val < 1 or guess_val > settings['max_number']:
        return jsonify({'status': 'warning', 'message': f"⚠️ Stay between 1 and {settings['max_number']}."})

    session['attempts'] += 1
    
    if guess_val == correct_num:
        time_taken = int(time.time() - session['game_start_time'])
        save_score(session['username'], settings['points'], won=True)
        
        new_title = get_title(session['points'])
        if check_if_the_one(session['username'], session['points']):
            session['is_the_one'] = True
            new_title = "THE ONE"
            
        clear_game_state()
        return jsonify({
            'status': 'win',
            'message': f"✅ The number was {correct_num} ({time_taken}s).",
            'new_points': session['points'],
            'new_title': new_title
        })
        
    elif session['attempts'] >= settings['max_attempts']:
        save_score(session['username'], 0, won=False)
        clear_game_state()
        return jsonify({
            'status': 'lose',
            'message': f"❌ Game Over! The number was {correct_num}."
        })
        
    else:
        hint = "⬆️ Higher" if guess_val < correct_num else "⬇️ Lower"
        return jsonify({
            'status': 'continue',
            'message': f"❌ Wrong. {hint}",
            'attempts_left': settings['max_attempts'] - session['attempts'],
            'history': history
        })

@app.route('/api/leaderboard')
def get_leaderboard_data():
    if not supabase: return jsonify([])
    try:
        response = supabase.table('leaderboard').select('username', 'points').order('points', desc=True).limit(100).execute()
        data = []
        for index, p in enumerate(response.data):
            title = "THE ONE" if index == 0 else get_title(p['points'])
            data.append({'username': p['username'], 'points': p['points'], 'title': title})
        return jsonify(data)
    except Exception:
        return jsonify([])

@app.route('/api/stats')
@login_required
def get_stats():
    pts = session.get('points', 0)
    current_title = "THE ONE" if session.get('is_the_one') else get_title(pts)
    return jsonify({
        'points': pts,
        'total_games': session.get('total_games', 0),
        'correct_guesses': session.get('correct_guesses', 0),
        'title': current_title
    })

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)