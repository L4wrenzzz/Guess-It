import os
import random
import time
import re
import logging
import threading
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from the .env file (safe way to store keys)
load_dotenv()

# Disable Blackfire APM by default unless specifically enabled
os.environ['BLACKFIRE_APM_ENABLED'] = '0' 

# Check if Blackfire profiler (performance monitoring) should be enabled
if os.environ.get('ENABLE_BLACKFIRE') == '1':
    try:
        import blackfire
        blackfire.patch_all() 
        print("✅ Blackfire Profiler Loaded (APM Disabled)")
    except Exception as exception:
        print(f"⚠️ Blackfire failed to load: {exception}")

from flask import Flask, render_template, request, session, jsonify
from werkzeug.exceptions import HTTPException
from supabase import create_client, Client
from cryptography.fernet import Fernet

app = Flask(__name__)

# Secret key is needed for signing session cookies so they can't be tampered with
app.secret_key = os.environ['SECRET_KEY']

# Initialize the encryption system (Fernet) to hide the target number in the session
def initialize_cipher():
    key = os.environ.get('FERNET_KEY')
    if not key:
        app.logger.warning("FERNET_KEY not found in .env. Generating temporary key.")
        return Fernet(Fernet.generate_key())
    return Fernet(key.encode())

cipher_suite = initialize_cipher()

# Global variable to hold the database connection
_db_client = None

# Singleton pattern to get the DB connection (reconnects if missing)
def get_db():
    global _db_client
    if _db_client:
        return _db_client
    
    # Fetch Supabase credentials from environment variables
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # Validate credentials
    if not url or not key:
        app.logger.error("Supabase credentials missing in .env")
        return None
        
    try:
        _db_client = create_client(url, key)
        return _db_client
    except Exception as exception:
        app.logger.error(f"DB Connection Attempt Failed: {exception}", exc_info=True)
        return None

# --- Caching Systems ---
# We use caching to prevent spamming the database with requests every second
CACHE_TIMEOUT = 60  # seconds

# Cache for "Who is the top player?" (Used in Login to check for "THE ONE")
TOP_PLAYER_CACHE = {
    'username': None,
    'last_updated': 0
}

# Cache for the full Leaderboard list so we don't fetch 100 rows every time someone clicks the tab
LEADERBOARD_CACHE = {
    'data': [],
    'last_updated': 0
}

# Security config for cookies (strict in production, relaxed in dev)
is_prod = os.environ.get('FLASK_ENV') == 'production'
app.config.update(
    SESSION_COOKIE_SECURE=is_prod, # Only send cookies over HTTPS in prod
    SESSION_COOKIE_HTTPONLY=True,  # JavaScript cannot access the cookie (prevents XSS theft)
    SESSION_COOKIE_SAMESITE='Lax', # Prevents CSRF attacks
)

# Game configuration: Defines the rules for each difficulty level
DIFFICULTY_SETTINGS = {
    'easy':       {'max_number': 10,        'max_attempts': 3,  'points': 3},
    'medium':     {'max_number': 100,       'max_attempts': 8,  'points': 10},
    'hard':       {'max_number': 1000,      'max_attempts': 15, 'points': 20},
    'impossible': {'max_number': 100000,    'max_attempts': 25, 'points': 45},
    'million':    {'max_number': 1000000,   'max_attempts': 50, 'points': 150},
}

# Titles awarded based on total points accumulated
TITLES = [
    ("Newbie", 100), ("Rookie", 500), ("Pro", 2500), 
    ("Legend", 5000), ("Champion", 10000)
]

# Adds security headers to every response sent back to the browser
@app.after_request
def add_security_headers(response):
    # CSP: Tells browser to only allow scripts/images from specific trusted sources
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " 
        "font-src 'self' https://fonts.gstatic.com; " 
        "script-src 'self' 'unsafe-inline'; " 
        "frame-src 'self' https://blackfire.io;"
    )
    # Prevents browser from guessing content types (security best practice)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Prevents this site from being embedded in an iframe (prevents Clickjacking)
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Disable caching for API calls so game state is always fresh
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
    return response

# Decorator to protect routes that require a logged-in user
def login_required(function_to_decorate):
    @wraps(function_to_decorate)
    def decorated_function(*args, **kwargs):
        if not session.get('username'):
            return jsonify({'error': 'Unauthorized', 'message': 'Please login first.'}), 401
        return function_to_decorate(*args, **kwargs)
    return decorated_function

# Global error handler to return JSON instead of HTML on crash
@app.errorhandler(Exception)
def handle_exception(exception):
    if isinstance(exception, HTTPException):
        return jsonify(error=exception.name, message=exception.description), exception.code
    app.logger.error(f"Unhandled Exception: {exception}", exc_info=True)
    return jsonify(error="Internal Server Error", message="Something went wrong."), 500

# Background task to save score (Threaded)
# We do this so the user doesn't have to wait for the DB write to finish before seeing "You Won"
def _save_score_bg(username, points_to_add, won):
    """Background task to save score to DB without blocking the user."""
    db = get_db()
    if db:
        try:
            # Calls the SQL function 'update_score' stored in Supabase
            db.rpc('update_score', {
                'p_username': username, 
                'p_points': points_to_add, 
                'p_won': won
            }).execute()
            app.logger.info(f"Background save success for {username}")
        except Exception as exception:
            app.logger.error(f"DB Save Failed for {username}: {exception}", exc_info=True)

def save_score(username, points_to_add, won=False):
    """Updates session immediately and spawns background thread for DB."""
    # 1. Optimistic Update: Update the session cookie immediately so the UI feels instant
    session['points'] = session.get('points', 0) + points_to_add
    session['total_games'] = session.get('total_games', 0) + 1
    if won:
        session['correct_guesses'] = session.get('correct_guesses', 0) + 1
    
    # 2. Fire and Forget: Start a background thread to update the actual database
    thread = threading.Thread(target=_save_score_bg, args=(username, points_to_add, won), daemon=True)
    thread.start()

# Helper to determine user rank based on points
def get_title(points):
    for title, threshold in reversed(TITLES):
        if points >= threshold: return title
    return None

# Checks if the current user is the #1 player in the world
def check_if_the_one(username):
    """Checks if user is #1, using cache to avoid DB hits."""
    current_time = time.time()
    
    # 1. Check Cache first to save DB resources
    if TOP_PLAYER_CACHE['username'] and (current_time - TOP_PLAYER_CACHE['last_updated'] < CACHE_TIMEOUT):
        return TOP_PLAYER_CACHE['username'] == username

    # 2. Check DB if cache is empty or old
    db = get_db()
    if not db: return False
    
    try:
        response = db.table('leaderboard').select('username').order('points', desc=True).limit(1).execute()
        if response.data:
            top_user = response.data[0]['username']
            # Update Cache
            TOP_PLAYER_CACHE['username'] = top_user
            TOP_PLAYER_CACHE['last_updated'] = current_time
            return top_user == username
    except Exception as exception:
        app.logger.warning(f"Leaderboard check failed: {exception}")
        pass
        
    return False

# Sets default values for a new user session
def init_session_defaults():
    defaults = {
        'points': 0, 'total_games': 0, 'correct_guesses': 0,
        'difficulty': 'easy', 'attempts': 0, 'game_ready': False,
        'guess_history': [], 'is_the_one': False, 'offline_mode': False
    }
    for k, v in defaults.items():
        session.setdefault(k, v)

# Anti-Cheat: If user refreshes or leaves mid-game, this counts as a loss
def forfeit_if_active():
    if session.get('game_ready') and 'target_token' in session:
        username = session.get('username')
        if username:
            save_score(username, 0, won=False)
            app.logger.info(f"Player {username} forfeited a game.")

# Cleans up game-specific session data
def clear_game_state():
    session.pop('target_token', None)
    session.pop('game_start_time', None)
    session['game_ready'] = False
    session['attempts'] = 0
    
# --- Routes ---

@app.route('/')
def index():
    # If they refresh the page while playing, they forfeit
    if session.get('game_ready'):
         forfeit_if_active()
         clear_game_state()
         
    init_session_defaults()
    user_title = None
    
    # Calculate title for display on the homepage
    if session.get('username'):
        user_points = session.get('points', 0)
        user_title = get_title(user_points)
        if session.get('is_the_one'): user_title = "THE ONE"

    # Render the main page
    return render_template('index.html', 
                           username=session.get('username'), 
                           user_title=user_title,
                           titles=TITLES)

@app.route('/api/login', methods=['POST'])
def login():
    if not request.is_json: return jsonify({'error': 'Invalid Content-Type'}), 400
    data = request.get_json()
    username = str(data.get('username', '')).strip()[:12]
    
    # Validation: Only allow alphanumeric usernames
    if not username or not re.match("^[a-zA-Z0-9]+$", username):
        return jsonify({'message': 'Invalid username.'}), 400
    
    session['username'] = username
    current_title = None
    session['offline_mode'] = False

    db_connected = False
    db = get_db()
    if db:
        try:
            # Fetch user stats from DB
            response = db.table('leaderboard').select('*').eq('username', username).execute()
            if response.data:
                user = response.data[0]
                session['points'] = user.get('points', 0)
                session['total_games'] = user.get('total_games', 0)
                session['correct_guesses'] = user.get('correct_guesses', 0)
                
                current_title = get_title(session['points'])
                if check_if_the_one(username):
                    session['is_the_one'] = True
                    current_title = "THE ONE"
                else:
                    session['is_the_one'] = False
            db_connected = True
        except Exception as exception:
            app.logger.error(f"DB Error during Login: {exception}", exc_info=True)
            db_connected = False

    # Fallback to offline mode if DB is down (lets user play without saving)
    if not db_connected:
        session['offline_mode'] = True
        session['points'] = 0
        session['total_games'] = 0
        session['correct_guesses'] = 0
        current_title = "Newbie"
    
    app.logger.info(f"User login: {username} (Offline Mode: {session['offline_mode']})")
    
    return jsonify({
        'success': True, 
        'points': session.get('points', 0), 
        'title': current_title,
        'offline': session.get('offline_mode', False)
    })

@app.route('/api/difficulty', methods=['POST'])
@login_required
def set_difficulty():
    # Changing difficulty mid-game resets the current game
    forfeit_if_active()
    clear_game_state()
    
    # Validate and set new difficulty
    data = request.get_json(silent=True) or {}
    new_difficulty = data.get('difficulty', 'easy')
    if new_difficulty not in DIFFICULTY_SETTINGS:
        return jsonify({'message': 'Invalid difficulty'}), 400

    # Set the new difficulty in session
    session['difficulty'] = new_difficulty
    return jsonify({
        'message': f"Difficulty set to {session['difficulty'].capitalize()}.",
        'max_number': DIFFICULTY_SETTINGS[session['difficulty']]['max_number']
    })

@app.route('/api/start', methods=['POST'])
@login_required
def start_game():
    forfeit_if_active()
    clear_game_state()
    
    settings = DIFFICULTY_SETTINGS[session.get('difficulty', 'easy')]
    target_number = random.randint(1, settings['max_number'])
    
    try:
        # ENCRYPT the target number before storing it in the session
        # This prevents the user from decoding their cookies to cheat
        encrypted_target = cipher_suite.encrypt(str(target_number).encode()).decode()
        session['target_token'] = encrypted_target
    except Exception as exception:
        app.logger.critical(f"Encryption failed: {exception}", exc_info=True)
        return jsonify({'error': 'Server Error', 'message': 'Game failed to start.'}), 500
    
    session['attempts'] = 0
    session['game_ready'] = True
    session['game_start_time'] = time.time()
    session['guess_history'] = []
    
    return jsonify({
        'message': "Game Started! Have fun guessing!",
        'game_ready': True,
        'max_number': settings['max_number']
    })

# API to handle a guess submission
@app.route('/api/guess', methods=['POST'])
@login_required
def guess():
    if not session.get('game_ready') or 'target_token' not in session:
        return jsonify({'error': 'State Error', 'message': 'Game not started'}), 400

    # Rate Limiting: Prevent bots from guessing instantly
    current_time = time.time()
    last_guess = session.get('last_guess_time', 0)
    if current_time - last_guess < 0.3:
        return jsonify({'status': 'warning', 'message': "⚠️ Slow down! Too fast."})
    session['last_guess_time'] = current_time

    data = request.get_json(silent=True)
    try:
        guess_value = int(data.get('guess'))
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': "⚠️ Invalid number."}), 400

    try:
        # Decrypt the target number to compare against the guess
        target_token = session['target_token']
        correct_num = int(cipher_suite.decrypt(target_token.encode()).decode())
    except Exception as exception:
        app.logger.error(f"Decryption failed or session invalid: {exception}", exc_info=True)
        return jsonify({'error': 'Security Error', 'message': 'Session invalid. Restart game.'}), 400

    settings = DIFFICULTY_SETTINGS[session['difficulty']]
    
    history = session.get('guess_history', [])
    history.append(guess_value)
    session['guess_history'] = history
    
    if guess_value < 1 or guess_value > settings['max_number']:
        return jsonify({'status': 'warning', 'message': f"⚠️ Stay between 1 and {settings['max_number']}."})

    session['attempts'] += 1
    
    # WIN CONDITION
    if guess_value == correct_num:
        time_taken = int(time.time() - session['game_start_time'])
        
        # Async Save (Fast)
        save_score(session['username'], settings['points'], won=True)
        
        new_title = get_title(session['points'])
        if session.get('offline_mode'):
            pass
        elif check_if_the_one(session['username']):
            session['is_the_one'] = True
            new_title = "THE ONE"
            
        clear_game_state()
        return jsonify({
            'status': 'win',
            'message': f"✅ The number was {correct_num} ({time_taken}s).",
            'new_points': session['points'],
            'new_title': new_title
        })
        
    # LOSE CONDITION (Max attempts reached)
    elif session['attempts'] >= settings['max_attempts']:
        save_score(session['username'], 0, won=False)
        clear_game_state()
        return jsonify({
            'status': 'lose',
            'message': f"❌ Game Over! The number was {correct_num}."
        })
        
    # WRONG GUESS (Continue)
    else:
        hint = "⬆️ Higher" if guess_value < correct_num else "⬇️ Lower"
        return jsonify({
            'status': 'continue',
            'message': f"❌ Wrong. {hint}",
            'attempts_left': settings['max_attempts'] - session['attempts'],
            'history': history
        })

# API to get the leaderboard data
@app.route('/api/leaderboard')
def get_leaderboard_data():
    """Fetch leaderboard with 60-second caching."""
    current_time = time.time()
    
    # 1. Return cached data if valid (Server-Side Caching)
    if LEADERBOARD_CACHE['data'] and (current_time - LEADERBOARD_CACHE['last_updated'] < CACHE_TIMEOUT):
        return jsonify(LEADERBOARD_CACHE['data'])
    
    # 2. Fetch from DB if cache expired
    db = get_db()
    if not db: 
        # Fallback to cache even if expired if DB is down
        if LEADERBOARD_CACHE['data']:
            return jsonify(LEADERBOARD_CACHE['data'])
        return jsonify({'error': 'db_down'})
    
    try:
        response = db.table('leaderboard').select('username', 'points').order('points', desc=True).limit(100).execute()
        data = []
        for index, player_entry in enumerate(response.data):
            # First place gets the special "THE ONE" title
            title = "THE ONE" if index == 0 else get_title(player_entry['points'])
            data.append({'username': player_entry['username'], 'points': player_entry['points'], 'title': title})
        
        # 3. Update Cache
        LEADERBOARD_CACHE['data'] = data
        LEADERBOARD_CACHE['last_updated'] = current_time
        
        return jsonify(data)
        # 4. Handle DB errors gracefully
    except Exception as exception:
        app.logger.error(f"Leaderboard fetch failed: {exception}", exc_info=True)
        return jsonify({'error': 'db_down'})

# API to get current user stats
@app.route('/api/stats')
@login_required
def get_stats():
    user_points = session.get('points', 0)
    current_title = "THE ONE" if session.get('is_the_one') else get_title(user_points)
    return jsonify({
        'points': user_points,
        'total_games': session.get('total_games', 0),
        'correct_guesses': session.get('correct_guesses', 0),
        'title': current_title,
        'offline': session.get('offline_mode', False)
    })

@app.route('/logout')
def logout():
    # If they logout mid-game, they forfeit
    forfeit_if_active()
    session.clear() # Wipes the cookie
    return jsonify({'success': True})

# --- Run the App ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)