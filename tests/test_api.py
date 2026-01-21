import json

def test_homepage_loads(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Guess It" in response.data

def test_login_invalid_username(client):
    # Test Empty Username
    response = client.post('/api/login', json={'username': ''})
    assert response.status_code == 400
    
    # Test Special Characters (Security Check)
    response = client.post('/api/login', json={'username': 'Hacker$$$'})
    assert response.status_code == 400

def test_login_success(client):
    # Test Valid Login
    response = client.post('/api/login', json={'username': 'Student1'})
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['title'] == None # New offline users default to None title

def test_game_flow(client):
    # 1. Login
    client.post('/api/login', json={'username': 'Player1'})
    
    # 2. Start Game
    response = client.post('/api/start')
    assert response.status_code == 200
    
    # 3. Make a Guess
    response = client.post('/api/guess', json={'guess': 5})
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'message' in data
    assert 'status' in data

def test_logout(client):
    # 1. Login first
    client.post('/api/login', json={'username': 'TestPlayer'})
    
    # 2. Logout
    response = client.get('/logout')
    assert response.status_code == 200
    
    # 3. Try to access a protected route (should fail/return 401)
    response = client.post('/api/start')
    assert response.status_code == 401

def test_change_difficulty(client):
    client.post('/api/login', json={'username': 'TestPlayer'})
    
    # Change to 'hard'
    response = client.post('/api/difficulty', json={'difficulty': 'hard'})
    assert response.status_code == 200
    data = response.get_json()
    
    # Check if the max number updated to 1000 (Hard mode)
    assert data['max_number'] == 1000

def test_guess_without_starting(client):
    """Test guessing before clicking start"""
    client.post('/api/login', json={'username': 'SadPathUser'})
    response = client.post('/api/guess', json={'guess': 50})
    
    assert response.status_code == 400
    assert b"Game not started" in response.data

def test_invalid_guess_input(client):
    """Test sending text instead of numbers"""
    client.post('/api/login', json={'username': 'SadPathUser'})
    client.post('/api/start')
    
    # Send "ABC" instead of a number
    response = client.post('/api/guess', json={'guess': "ABC"})
    assert response.status_code == 400
    assert b"Invalid number" in response.data
    
    # Send negative number (optional check if you want to enforce it)
    # response = client.post('/api/guess', json={'guess': -5})

def test_db_offline_behavior(client):
    """Simulate Database failure"""
    from flask import current_app
    
    # Manually break the DB client for this test
    with client.application.app_context():
        current_app.supabase_client = None

    client.post('/api/login', json={'username': 'OfflineUser'})
    
    # Should return success but with offline=True
    response = client.get('/api/stats')
    data = response.get_json()
    
    assert response.status_code == 200
    assert data['offline'] is True