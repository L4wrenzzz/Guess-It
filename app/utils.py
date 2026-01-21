import threading

class LocalThreadQueue:
    """
    A simple background task runner using Python threads.
    Used when Redis is not available (e.g., in Development).
    """
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