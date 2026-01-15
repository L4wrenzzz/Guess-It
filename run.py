import os
from app import create_app

# --- Blackfire Configuration ---
# We configure this before creating the app so it can hook into everything.
# On Windows, ensure you have the Blackfire agent installed if you want to test this locally.
if os.environ.get('ENABLE_BLACKFIRE') == '1':
    try:
        import blackfire
        blackfire.patch_all()
        print("✅ Blackfire Profiler Loaded")
    except Exception as error:
        print(f"⚠️ Blackfire failed to load: {error}")

# Create the app
application = create_app()

if __name__ == '__main__':
    # If running locally on Windows via 'python run.py'
    port = int(os.environ.get("PORT", 5000))
    application.run(host='0.0.0.0', port=port, debug=True)