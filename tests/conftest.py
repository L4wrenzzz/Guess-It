import pytest
import os
from app import create_app

# The name 'conftest.py' is magic in Pytest.
# It tells Pytest: "Run this code before you run any actual tests."

@pytest.fixture
def client():
    """
    This function sets up a 'fake' version of our app for testing.
    It simulates a web browser without needing to run the actual server.
    """
    # Setup Fake Config
    os.environ['SECRET_KEY'] = 'test_secret_key'
    # We need a fake encryption key for tests to pass
    os.environ['FERNET_KEY'] = 'test_fernet_key_must_be_url_safe_base64_encoded_value='
    
    application = create_app()
    
    # Enable Testing Mode (Disables some security checks)
    application.config['TESTING'] = True
    application.config['RATELIMIT_ENABLED'] = False  # We don't want rate limits during tests
    
    # Create the test client
    with application.test_client() as test_client:
        with application.app_context():
            yield test_client  # This is where the testing happens