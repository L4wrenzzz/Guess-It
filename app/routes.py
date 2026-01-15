import time
import random
import re
from functools import wraps
from flask import Blueprint, Response, render_template, request, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.database import get_database_client
from app import limiter
from app.config import GameConfig
from cryptography.fernet import InvalidToken

# Create a Blueprint. This is like a "mini-app" that holds our routes.
# It helps keep the code organized separate from the setup code.
main_blueprint = Blueprint('main', __name__)

# --- Constants ---
# How long (in seconds) we keep the leaderboard in memory before refreshing from DB
CACHE_TIMEOUT_SECONDS = 60

# --- Memory Cache ---
# We use simple dictionaries to store data in memory (RAM).
# This reduces the number of times we have to ask the database for data.
TOP_PLAYER_CACHE = {'username': None, 'last_updated': 0}
LEADERBOARD_CACHE = {'data': [], 'last_updated': 0}

# --- Helper Functions ---

# Background Task: Saves the score to the database.
# We run this in a separate thread so the user doesn't have to wait for the DB to finish.
def _save_score_background_task(username: str, points: int, won: bool):
    # Update the real database
    database_client = get_database_client()
    if database_client:
        try:
            database_client.rpc('update_score', {
                'p_username': username, 
                'p_points': points, 
                'p_won': won
            }).execute()
        except InvalidToken as error:
            current_app.logger.error(f"[Background Task] Score Save Failed: {error}")

def save_score_async(username: str, points_to_add: int, won: bool = False):
    """
    Updates the session (instant feedback) and starts a background thread 
    to update the real database (persistent storage).
    """
    # 1. Update Session (Optimistic UI)
    session['points'] = session.get('points', 0) + points_to_add
    session['total_games'] = session.get('total_games', 0) + 1
    if won:
        session['correct_guesses'] = session.get('correct_guesses', 0) + 1
    
    current_app.task_queue.enqueue(
        _save_score_background_task,
        username=username, 
        points=points_to_add, 
        won=won
    )

def get_player_title(points: int) -> str | None:
    # Calculates the title based on points.
    for title_name, threshold in reversed(GameConfig.TITLES):
        if points >= threshold: return title_name
    return None

def check_if_user_is_the_one(username: str) -> bool:
    # Checks if the user is the #1 player.
    # Uses caching to prevent spamming the DB with queries.
    current_time = time.time()
    
    # Check Cache First
    if TOP_PLAYER_CACHE['username'] and (current_time - TOP_PLAYER_CACHE['last_updated'] < CACHE_TIMEOUT_SECONDS):
        return TOP_PLAYER_CACHE['username'] == username

    # If Cache expired, check Database
    database_client = get_database_client()
    if not database_client: return False
    
    try:
        response = database_client.table('leaderboard').select('username').order('points', desc=True).limit(1).execute()
        if response.data:
            top_user = response.data[0]['username']
            # Update Cache
            TOP_PLAYER_CACHE['username'] = top_user
            TOP_PLAYER_CACHE['last_updated'] = current_time
            return top_user == username
    except InvalidToken:
        pass
    return False

def initialize_session_defaults():
    # Sets up empty values for a new user session.
    default_values = {
        'points': 0, 'total_games': 0, 'correct_guesses': 0,
        'difficulty': 'easy', 'attempts': 0, 'game_ready': False,
        'guess_history': [], 'is_the_one': False, 'offline_mode': False
    }
    for key, value in default_values.items():
        session.setdefault(key, value)

def forfeit_game_if_active():
    # Anti-Cheat: If user leaves mid-game, count it as a loss.
    if session.get('game_ready') and 'target_token' in session:
        username = session.get('username')
        if username:
            save_score_async(username, 0, won=False)

def clear_game_state():
    # Removes sensitive game data (like the target number) from the session.
    session.pop('target_token', None)
    session.pop('game_start_time', None)
    session['game_ready'] = False
    session['attempts'] = 0

# --- Routes (API Endpoints) ---

@main_blueprint.after_request
def add_security_headers(response: Response) -> Response:
    # Adds HTTP headers that tell the browser to enable security features.
    
    # We added 'frame-src' to allow Blackfire's toolbar to load.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "frame-src 'self' https://blackfire.io;"
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@main_blueprint.route('/')
def index_page():
    # If they refresh the page while playing, they forfeit the current game
    if session.get('game_ready'):
         forfeit_game_if_active()
         clear_game_state()
         
    initialize_session_defaults()
    
    user_title = None
    if session.get('username'):
        user_points = session.get('points', 0)
        user_title = get_player_title(user_points)
        if session.get('is_the_one'): user_title = "THE ONE"

    return render_template('index.html', username=session.get('username'), user_title=user_title, titles=GameConfig.TITLES)

@main_blueprint.route('/api/login', methods=['POST'])
def handle_login() -> Response:
    request_data = request.get_json() or {}
    username = str(request_data.get('username', '')).strip()[:12]
    
    # Validation: Only letters and numbers allowed
    if not username or not re.match("^[a-zA-Z0-9]+$", username):
        return jsonify({'message': 'Invalid username.'}), 400
    
    user = User(username=username)
    login_user(user, remember=True)
    
    session['username'] = username
    current_title = None
    session['offline_mode'] = False

    database_client = get_database_client()
    if database_client:
        try:
            # Fetch user stats from DB
            response = database_client.table('leaderboard').select('*').eq('username', username).execute()
            if response.data:
                user_data = response.data[0]
                session['points'] = user_data.get('points', 0)
                session['total_games'] = user_data.get('total_games', 0)
                session['correct_guesses'] = user_data.get('correct_guesses', 0)
                
                # Check for titles
                current_title = "THE ONE" if check_if_user_is_the_one(username) else get_player_title(session['points'])
                session['is_the_one'] = (current_title == "THE ONE")

            else:
                current_title = None
                session['points'] = 0

        except InvalidToken as error:
            current_app.logger.error(f"Login Database Error: {error}")
            session['offline_mode'] = True
    else:
        # If DB is down, allow playing in Offline Mode
        session['offline_mode'] = True
        current_title = None

    if session['offline_mode']:
        session['points'] = 0

    return jsonify({
        'success': True,
        'points': session.get('points', 0),
        'title': current_title, 
        'offline': session['offline_mode']
    })

@main_blueprint.route('/api/difficulty', methods=['POST'])
@login_required
def set_difficulty_level() -> Response:
    # Changing difficulty mid-game counts as a loss
    forfeit_game_if_active()
    clear_game_state()
    
    request_data = request.get_json(silent=True) or {}
    new_difficulty = request_data.get('difficulty', 'easy')
    
    if new_difficulty not in GameConfig.DIFFICULTY_SETTINGS:
        return jsonify({'message': 'Invalid difficulty'}), 400
        
    session['difficulty'] = new_difficulty
    return jsonify({
        'message': f"Difficulty set to {new_difficulty.capitalize()}.",
        'max_number': GameConfig.DIFFICULTY_SETTINGS[new_difficulty]['max_number']
    })

@main_blueprint.route('/api/start', methods=['POST'])
@login_required
def start_game() -> Response:
    forfeit_game_if_active()
    clear_game_state()
    
    settings = GameConfig.DIFFICULTY_SETTINGS[session.get('difficulty', 'easy')]
    target_number = random.randint(1, settings['max_number'])
    
    # Encryption Step:
    # We encrypt the target number before storing it in the user's cookie.
    # This prevents the user from decoding their cookie to cheat.
    encrypted_token = current_app.cipher_suite.encrypt(str(target_number).encode()).decode()
    session['target_token'] = encrypted_token
    
    session['attempts'] = 0
    session['game_ready'] = True
    session['game_start_time'] = time.time()
    session['guess_history'] = []
    
    return jsonify({'message': "Game Started!", 'game_ready': True, 'max_number': settings['max_number']})

@main_blueprint.route('/api/guess', methods=['POST'])
@login_required
@limiter.limit("3 per second") # Rate Limit: Only 3 guesses per second allowed
def process_guess() -> Response:
    if not session.get('game_ready') or 'target_token' not in session:
        return jsonify({'error': 'State Error', 'message': 'Game not started'}), 400

    request_data = request.get_json(silent=True) or {}
    try:
        guess_value = int(request_data.get('guess'))
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': "Invalid number."}), 400

    try:
        # Decrypt the target number from the session
        token = session['target_token']
        correct_number = int(current_app.cipher_suite.decrypt(token.encode()).decode())
    except InvalidToken:
        current_app.logger.warning(f"Security Alert: Invalid Token for {session.get('username')}")
        return jsonify({'error': 'Security Error', 'message': 'Invalid Session Token.'}), 400
    except Exception as e:
        current_app.logger.error(f"Decryption Error: {e}")
        return jsonify({'error': 'Server Error', 'message': 'An error occurred.'}), 500

    settings = GameConfig.DIFFICULTY_SETTINGS[session.get('difficulty', 'easy')]
    
    # Update History
    history = session.get('guess_history', [])
    history.append(guess_value)
    session['guess_history'] = history
    session.modified = True # Tell Flask the session data changed
    
    session['attempts'] += 1
    
    # WIN Logic
    if guess_value == correct_number:
        time_taken = int(time.time() - session['game_start_time'])
        
        save_score_async(session['username'], settings['points'], won=True)
        
        new_title = "THE ONE" if check_if_user_is_the_one(session['username']) else get_player_title(session['points'])
        clear_game_state()
        
        return jsonify({
            'status': 'win',
            'message': f"✅ The number was {correct_number} ({time_taken}s).",
            'new_points': session['points'],
            'new_title': new_title
        })
        
    # LOSE Logic
    elif session['attempts'] >= settings['max_attempts']:
        save_score_async(session['username'], 0, won=False)
        clear_game_state()
        return jsonify({'status': 'lose', 'message': f"❌ Game Over! The number was {correct_number}."})
        
    # CONTINUE Logic
    else:
        hint_text = "Higher" if guess_value < correct_number else "Lower"
        return jsonify({
            'status': 'continue',
            'message': f"❌ Wrong. ⬆️ {hint_text}",
            'attempts_left': settings['max_attempts'] - session['attempts'],
            'history': session['guess_history']
        })

@main_blueprint.route('/api/leaderboard')
def get_leaderboard_data() -> Response:
    current_time = time.time()
    
    # Check Cache first (Server-side caching)
    if LEADERBOARD_CACHE['data'] and (current_time - LEADERBOARD_CACHE['last_updated'] < CACHE_TIMEOUT_SECONDS):
        return jsonify(LEADERBOARD_CACHE['data'])
    
    database_client = get_database_client()
    if not database_client:
        return jsonify(LEADERBOARD_CACHE['data']) if LEADERBOARD_CACHE['data'] else jsonify({'error': 'db_down'})
    
    try:
        response = database_client.table('leaderboard').select('username', 'points').order('points', desc=True).limit(100).execute()
        leaderboard_data = []
        for index, player in enumerate(response.data):
            # Rank 1 gets "THE ONE", others get normal titles
            title = "THE ONE" if index == 0 else get_player_title(player['points'])
            leaderboard_data.append({
                'username': player['username'], 
                'points': player['points'], 
                'title': title
            })
        
        # Update Cache
        LEADERBOARD_CACHE['data'] = leaderboard_data
        LEADERBOARD_CACHE['last_updated'] = current_time
        return jsonify(leaderboard_data)
    except InvalidToken:
        return jsonify({'error': 'db_down'})

@main_blueprint.route('/api/stats')
@login_required
def get_user_stats() -> Response:
    user_points = session.get('points', 0)
    current_title = "THE ONE" if session.get('is_the_one') else get_player_title(user_points)
    return jsonify({
        'points': user_points, 
        'total_games': session.get('total_games', 0),
        'correct_guesses': session.get('correct_guesses', 0),
        'title': current_title, 
        'offline': session.get('offline_mode', False)
    })

@main_blueprint.route('/logout')
def handle_logout() -> Response:
    # Warns the user if they are in the middle of a game
    forfeit_game_if_active()
    # Logs out the user and clears the session.
    logout_user()

    session.clear()
    return jsonify({'success': True})