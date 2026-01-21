import os
import threading
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from redis import Redis, ConnectionError
from rq import Queue

from app.utils import LocalThreadQueue

# Smart Storage Selection
storage_uri = os.environ.get("REDIS_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=storage_uri, 
    default_limits=["200 per day", "50 per hour"]
)

def create_app():
    load_dotenv()

    application = Flask(__name__, static_folder='../static', template_folder='../templates')
    limiter.init_app(application)

    # --- Production Security Check ---
    is_production = os.environ.get('FLASK_ENV') == 'production'
    secret_key = os.environ.get('SECRET_KEY')
    fernet_key = os.environ.get('FERNET_KEY')

    if is_production:
        if not secret_key:
            raise ValueError("CRITICAL: SECRET_KEY is missing in Production environment.")
        # We handle fernet_key specific logic below

    application.secret_key = secret_key

    # --- Initialize Encryption (Fernet) ---
    if not fernet_key:
        # STRICT MODE: Fail if key is missing (As requested)
        raise ValueError("CRITICAL: FERNET_KEY is missing. Cannot start securely.")
    
    application.cipher_suite = Fernet(fernet_key.encode())

    # --- Login Manager Setup ---
    login_manager = LoginManager()
    login_manager.init_app(application)
    login_manager.login_view = 'main.handle_login'

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User(user_id)

    # --- Redis Setup ---
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    try:
        redis_conn = Redis.from_url(redis_url)
        redis_conn.ping() 
        application.task_queue = Queue(connection=redis_conn)
        print("✅ Redis Connected (Production Mode)")
        
        # Future Growth: If you ever build a massive app with millions of users, 
        # look into a task queue like Celery or RQ (which you already have in your requirements!) 
        # to run tasks on a completely different CPU process.

    except ConnectionError:
        print("⚠️ Redis not found. Using Local Threads (Dev Mode)")
        application.task_queue = LocalThreadQueue(application)

    application.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )

    from .routes import main_blueprint
    application.register_blueprint(main_blueprint)

    return application