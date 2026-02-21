import os
from app import create_app

# Create the app
application = create_app()

if __name__ == '__main__':
    # If running locally on Windows via 'python run.py'
    port = int(os.environ.get("PORT", 5000))
    application.run(host='0.0.0.0', port=port, debug=True)