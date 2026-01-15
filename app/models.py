from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, username, points=0):
        self.id = username  # Flask-Login uses 'id' to track users
        self.points = points