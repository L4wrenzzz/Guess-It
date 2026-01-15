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