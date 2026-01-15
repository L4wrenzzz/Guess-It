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

# Smart Storage Selection
# If REDIS_URL is in .env, use it. Otherwise, use computer memory (RAM).
storage_uri = os.environ.get("REDIS_URL", "memory://")

# We initialize the Rate Limiter here but connect it to the app later.
# This prevents users from spamming your API.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=storage_uri, 
    default_limits=["200 per day", "50 per hour"]
)

class LocalThreadQueue:
    def __init__(self, app_instance):
        self.app = app_instance

    def enqueue(self, func, **kwargs):
        # Wraps the background task in a thread and injects the App Context
        # so it has access to database configuration.
        def thread_wrapper(app, target_func, kwargs):
            with app.app_context():
                target_func(**kwargs)

        thread = threading.Thread(target=thread_wrapper, args=(self.app, func, kwargs))
        thread.start()

def create_app():
    # Load secret keys from the .env file
    load_dotenv()

    # Initialize the Flask application
    # We explicitly tell Flask where to find 'static' files and 'templates'
    # because this file is inside the 'app' folder, not the root.
    application = Flask(__name__, static_folder='../static', template_folder='../templates')
    limiter.init_app(application)

    login_manager = LoginManager()
    login_manager.init_app(application)
    login_manager.login_view = 'main.handle_login'

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User(user_id)

    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    try:
        # Try to connect to real Redis
        redis_conn = Redis.from_url(redis_url)
        redis_conn.ping() # Check if server is actually running
        application.task_queue = Queue(connection=redis_conn)
        print("✅ Redis Connected (Production Mode)")
    except ConnectionError:
        # Fallback to Local Threads if Redis is missing
        print("⚠️ Redis not found. Using Local Threads (Dev Mode)")
        application.task_queue = LocalThreadQueue(application)

    # The secret key is used to sign session cookies so they cannot be tampered with.
    application.secret_key = os.environ.get('SECRET_KEY')

    # Security Config: Simplified for Development
    # We removed the strict 'Secure' cookie check so it works easily on localhost.
    application.config.update(
        SESSION_COOKIE_HTTPONLY=True,  # JavaScript cannot steal the cookie
        SESSION_COOKIE_SAMESITE='Lax', # Protects against CSRF attacks
    )

    # Initialize Encryption (Fernet)
    # We attach 'cipher_suite' to the app so we can access it in routes.py
    fernet_key = os.environ.get('FERNET_KEY')
    if not fernet_key:
        print("WARNING: FERNET_KEY not found. Generating a temporary one.")
        application.cipher_suite = Fernet(Fernet.generate_key())
    else:
        application.cipher_suite = Fernet(fernet_key.encode())

    # Import and register the routes (the API logic)
    from .routes import main_blueprint
    application.register_blueprint(main_blueprint)

    return application