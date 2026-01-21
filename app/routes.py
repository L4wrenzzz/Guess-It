import time
import random
import re
import os
from functools import wraps
from flask import Blueprint, Response, render_template, request, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.database import get_database_client
from app import limiter
from app.config import GameConfig
from cryptography.fernet import InvalidToken
from app.schemas import LoginRequest, GuessRequest
from pydantic import ValidationError

# --- IMPORTS FOR WORKER ---
from supabase import create_client
from dotenv import load_dotenv

# Create a Blueprint. This is like a "mini-app" that holds our routes.
main_blueprint = Blueprint('main', __name__)

# --- Constants ---
CACHE_TIMEOUT_SECONDS = 5

# --- Memory Cache ---
# BOSS EDIT: Added 'points' to cache structure to fix the race condition logic
TOP_PLAYER_CACHE = {'username': None, 'points': 0, 'last_updated': 0}
LEADERBOARD_CACHE = {'data': [], 'last_updated': 0}

# --- Helper Functions ---

# FIXED: Independent Background Task
# This function now creates its own database connection so it doesn't crash 
# when running in the background worker (RQ).
def _save_score_background_task(username: str, points: int, won: bool):
    # 1. Load Environment Variables (Secrets)
    load_dotenv()
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # 2. Safety Check
    if not url or not key:
        print("❌ [Worker Error] Supabase credentials missing.")
        return

    try:
        # 3. Create a fresh connection specifically for this task
        # We don't use 'get_database_client()' here because that relies on Flask's 'g' context,
        # which doesn't exist inside the background worker process.
        supabase = create_client(url, key)
        
        supabase.rpc('update_score', {
            'p_username': username, 
            'p_points': points, 
            'p_won': won
        }).execute()
        
        # We use print() because 'current_app.logger' might not be available
        print(f"✅ [Worker] Saved score for {username}")
        
    except Exception as error:
        print(f"❌ [Worker Failed] {error}")

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
    
    # 2. Send task to the Queue
    # BOSS NOTE: Ensure task_queue is available (it should be via create_app)
    if hasattr(current_app, 'task_queue'):
        current_app.task_queue.enqueue(
            _save_score_background_task,
            username=username, 
            points=points_to_add, 
            won=won
        )

def get_player_title(points: int) -> str | None:
    for title_name, threshold in reversed(GameConfig.TITLES):
        if points >= threshold: return title_name
    return None

# BOSS FIX: Added 'current_user_points' to handle Optimistic UI check
def check_if_user_is_the_one(username: str, current_user_points: int = 0) -> bool:
    current_time = time.time()
    
    # 1. Retrieve cached top player info
    cached_top_user = TOP_PLAYER_CACHE['username']
    cached_top_points = TOP_PLAYER_CACHE.get('points', 0)
    
    # 2. If cache is expired or empty, fetch fresh data
    if not cached_top_user or (current_time - TOP_PLAYER_CACHE['last_updated'] > CACHE_TIMEOUT_SECONDS):
        database_client = get_database_client()
        if database_client:
            try:
                # BOSS FIX: We select 'points' as well to compare accurately
                response = database_client.table('leaderboard').select('username, points').order('points', desc=True).limit(1).execute()
                if response.data:
                    top_data = response.data[0]
                    cached_top_user = top_data['username']
                    cached_top_points = top_data['points']
                    
                    # Update Cache
                    TOP_PLAYER_CACHE['username'] = cached_top_user
                    TOP_PLAYER_CACHE['points'] = cached_top_points
                    TOP_PLAYER_CACHE['last_updated'] = current_time
            except InvalidToken:
                pass
    
    # 3. Optimistic Comparison
    # If I have more points NOW (in session) than the DB says the top player has,
    # I am "THE ONE", even if the DB hasn't updated yet.
    if current_user_points > cached_top_points:
        return True
        
    # Standard check
    return cached_top_user == username

def initialize_session_defaults():
    default_values = {
        'points': 0, 'total_games': 0, 'correct_guesses': 0,
        'difficulty': 'easy', 'attempts': 0, 'game_ready': False,
        'guess_history': [], 'is_the_one': False, 'offline_mode': False
    }
    for key, value in default_values.items():
        session.setdefault(key, value)

def forfeit_game_if_active():
    if session.get('game_ready') and 'target_token' in session:
        username = session.get('username')
        if username:
            save_score_async(username, 0, won=False)

def clear_game_state():
    session.pop('target_token', None)
    session.pop('game_start_time', None)
    session['game_ready'] = False
    session['attempts'] = 0

# --- Routes (API Endpoints) ---

@main_blueprint.after_request
def add_security_headers(response: Response) -> Response:
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
    if session.get('game_ready'):
         forfeit_game_if_active()
         clear_game_state()
         
    initialize_session_defaults()
    
    user_title = None
    if session.get('username'):
        user_points = session.get('points', 0)
        # Pass current points to ensure title is accurate
        is_the_one = check_if_user_is_the_one(session.get('username'), user_points)
        user_title = "THE ONE" if is_the_one else get_player_title(user_points)
        if is_the_one: session['is_the_one'] = True

    return render_template('index.html', username=session.get('username'), user_title=user_title, titles=GameConfig.TITLES)

@main_blueprint.route('/api/login', methods=['POST'])
def handle_login() -> Response:
    request_data = request.get_json() or {}
    
    try:
        validated_data = LoginRequest(**request_data)
        username = validated_data.username
    except ValidationError as e:
        return jsonify({'message': e.errors()[0]['msg']}), 400
    
    user = User(username=username)
    login_user(user, remember=True)
    
    session['username'] = username
    current_title = None
    session['offline_mode'] = False

    database_client = get_database_client()
    if database_client:
        try:
            response = database_client.table('leaderboard').select('*').eq('username', username).execute()
            if response.data:
                user_data = response.data[0]
                session['points'] = user_data.get('points', 0)
                session['total_games'] = user_data.get('total_games', 0)
                session['correct_guesses'] = user_data.get('correct_guesses', 0)
                
                # Check title with fresh data
                is_the_one = check_if_user_is_the_one(username, session['points'])
                current_title = "THE ONE" if is_the_one else get_player_title(session['points'])
                session['is_the_one'] = (current_title == "THE ONE")

            else:
                current_title = None
                session['points'] = 0

        except InvalidToken as error:
            current_app.logger.error(f"Login Database Error: {error}")
            session['offline_mode'] = True
    else:
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
    
    encrypted_token = current_app.cipher_suite.encrypt(str(target_number).encode()).decode()
    session['target_token'] = encrypted_token
    
    session['attempts'] = 0
    session['game_ready'] = True
    session['game_start_time'] = time.time()
    session['guess_history'] = []
    
    return jsonify({'message': "Game Started!", 'game_ready': True, 'max_number': settings['max_number']})

@main_blueprint.route('/api/guess', methods=['POST'])
@login_required
@limiter.limit("3 per second")
def process_guess() -> Response:
    if not session.get('game_ready') or 'target_token' not in session:
        return jsonify({'error': 'State Error', 'message': 'Game not started'}), 400

    request_data = request.get_json(silent=True) or {}
    try:
        validated_data = GuessRequest(**request_data)
        guess_value = validated_data.guess
    except ValidationError:
        return jsonify({'status': 'error', 'message': "Invalid number."}), 400

    try:
        token = session['target_token']
        correct_number = int(current_app.cipher_suite.decrypt(token.encode()).decode())
    except InvalidToken:
        current_app.logger.warning(f"Security Alert: Invalid Token for {session.get('username')}")
        return jsonify({'error': 'Security Error', 'message': 'Invalid Session Token.'}), 400
    except Exception as e:
        current_app.logger.error(f"Decryption Error: {e}")
        return jsonify({'error': 'Server Error', 'message': 'An error occurred.'}), 500

    settings = GameConfig.DIFFICULTY_SETTINGS[session.get('difficulty', 'easy')]
    
    history = session.get('guess_history', [])
    history.append(guess_value)
    session['guess_history'] = history
    session.modified = True 
    
    session['attempts'] += 1
    
    if guess_value == correct_number:
        time_taken = int(time.time() - session['game_start_time'])
        
        # NOTE: Updates session instantly, but DB update is async
        save_score_async(session['username'], settings['points'], won=True)
        
        # BOSS FIX: Use the updated session points for the check
        is_the_one = check_if_user_is_the_one(session['username'], session['points'])
        new_title = "THE ONE" if is_the_one else get_player_title(session['points'])
        
        # Persist this specific title flag for other routes
        session['is_the_one'] = (new_title == "THE ONE")
        
        clear_game_state()
        
        return jsonify({
            'status': 'win',
            'message': f"✅ The number was {correct_number} ({time_taken}s).",
            'new_points': session['points'],
            'new_title': new_title
        })
        
    elif session['attempts'] >= settings['max_attempts']:
        save_score_async(session['username'], 0, won=False)
        clear_game_state()
        return jsonify({'status': 'lose', 'message': f"❌ Game Over! The number was {correct_number}."})
        
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
    
    if LEADERBOARD_CACHE['data'] and (current_time - LEADERBOARD_CACHE['last_updated'] < CACHE_TIMEOUT_SECONDS):
        return jsonify(LEADERBOARD_CACHE['data'])
    
    database_client = get_database_client()
    if not database_client:
        return jsonify(LEADERBOARD_CACHE['data']) if LEADERBOARD_CACHE['data'] else jsonify({'error': 'db_down'})
    
    try:
        response = database_client.table('leaderboard').select('username', 'points').order('points', desc=True).limit(100).execute()
        leaderboard_data = []
        for index, player in enumerate(response.data):
            title = "THE ONE" if index == 0 else get_player_title(player['points'])
            leaderboard_data.append({
                'username': player['username'], 
                'points': player['points'], 
                'title': title
            })
            
            # Keep the top player cache in sync when we fetch the full leaderboard
            if index == 0:
                TOP_PLAYER_CACHE['username'] = player['username']
                TOP_PLAYER_CACHE['points'] = player['points']
                TOP_PLAYER_CACHE['last_updated'] = current_time
        
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
    forfeit_game_if_active()
    logout_user()
    session.clear()
    return jsonify({'success': True})