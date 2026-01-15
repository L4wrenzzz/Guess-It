import os
from flask import g, current_app
from supabase import create_client, Client

# Type Hinting: This function returns either a Supabase Client or None
def get_database_client() -> Client | None:
    # Returns the Supabase client for the current request.
    # If we cannot connect, it returns None (triggering Offline Mode).

    # 'g' is a global flask object specific to the *current request*.
    # We check if 'database_client' is already stored in 'g' to avoid reconnecting multiple times in a single request.
    if 'database_client' not in g:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        # If keys are missing, we log an error and return None
        if not url or not key:
            if not getattr(g, 'logged_missing_creds', False):
                current_app.logger.error("Supabase credentials missing in .env")
                g.logged_missing_creds = True
            return None
            
        try:
            # Create the connection and store it in 'g'
            g.database_client = create_client(url, key)
        except Exception as error:
            current_app.logger.error(f"Database Connection Attempt Failed: {error}")
            return None

    return g.database_client