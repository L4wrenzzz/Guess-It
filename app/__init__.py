import os
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# We initialize the Rate Limiter here but connect it to the app later.
# This prevents users from spamming your API.
# UPDATED: Smart Storage Selection
# If REDIS_URL is in .env, use it. Otherwise, use computer memory (RAM).
storage_uri = os.environ.get("REDIS_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=storage_uri, 
    default_limits=["200 per day", "50 per hour"]
)

def create_app():
    # Load secret keys from the .env file
    load_dotenv()
    
    # Initialize the Flask application
    # We explicitly tell Flask where to find 'static' files and 'templates'
    # because this file is inside the 'app' folder, not the root.
    application = Flask(__name__, static_folder='../static', template_folder='../templates')
    
    # The secret key is used to sign session cookies so they cannot be tampered with.
    application.secret_key = os.environ.get('SECRET_KEY', 'dev_default_key')

    # Security Config: Simplified for Development
    # We removed the strict 'Secure' cookie check so it works easily on localhost.
    application.config.update(
        SESSION_COOKIE_HTTPONLY=True,  # JavaScript cannot steal the cookie
        SESSION_COOKIE_SAMESITE='Lax', # Protects against CSRF attacks
    )

    # Attach the Rate Limiter to this specific app
    limiter.init_app(application)

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