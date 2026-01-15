class GameConfig:
    DIFFICULTY_SETTINGS = {
        'easy':       {'max_number': 10,        'max_attempts': 3,  'points': 3},
        'medium':     {'max_number': 100,       'max_attempts': 8,  'points': 10},
        'hard':       {'max_number': 1000,      'max_attempts': 15, 'points': 20},
        'impossible': {'max_number': 100000,    'max_attempts': 25, 'points': 45},
        'million':    {'max_number': 1000000,   'max_attempts': 50, 'points': 150},
    }

    TITLES = [
        ("Newbie", 100), ("Rookie", 500), ("Pro", 2500), 
        ("Legend", 5000), ("Champion", 10000)
    ]