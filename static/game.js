let timerInterval;
let startTime;
let currentAudio = null;
let maxNumber = 10; 

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast-msg');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast-msg toast-${type}`;
    toast.style.cssText = `
        position: fixed; top: 20px; right: 20px; 
        background: rgba(0,0,0,0.8); color: #fff; padding: 12px 24px; 
        border-radius: 8px; z-index: 1000; animation: fadeIn 0.3s;
        border-left: 4px solid ${type === 'error' ? '#ff5252' : '#00f260'};
    `;
    toast.innerText = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

window.addEventListener('offline', () => {
    showToast("⚠️ No Internet Connection", "error");
    toggleButtons(true);
});

window.addEventListener('online', () => {
    showToast("✅ Back Online", "success");
    toggleButtons(false);
});

function toggleButtons(disabled) {
    document.getElementById('start-btn').disabled = disabled;
    document.getElementById('submit-guess-btn').disabled = disabled;
}

function showSection(id) {
    ['game', 'stats', 'leaderboard', 'titles'].forEach(s => {
        document.getElementById('section-' + s).classList.add('hidden');
    });
    document.getElementById('section-' + id).classList.remove('hidden');
    playClick();
}

function playClick() {
    const s = document.getElementById('clickSound');
    s.currentTime = 0; s.play().catch(()=>{});
}

function playLoop(type) {
    stopLoop();
    currentAudio = document.getElementById(type + 'Sound');
    if(currentAudio) {
        currentAudio.loop = true;
        currentAudio.currentTime = 0;
        currentAudio.play().catch(e=>{});
    }
}

function stopLoop() {
    if(currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
    }
}

document.addEventListener('click', () => { if(currentAudio) stopLoop(); });
document.addEventListener('keydown', () => { if(currentAudio) stopLoop(); });

function updateTitleDisplay(title) {
    const titleEl = document.getElementById('display-title');
    const userEl = document.getElementById('display-username');

    if (!title) {
        titleEl.className = 'player-title hidden';
        titleEl.innerHTML = '';
        userEl.className = '';
        userEl.style.color = '';
        return;
    }

    titleEl.classList.remove('hidden');
    const formattedTitle = title.replace(' ', '-');

    if(title === "THE ONE") {
        titleEl.innerHTML = "<span>THE ONE</span>";
    } else {
        titleEl.innerText = title;
    }
    titleEl.className = 'player-title title-' + formattedTitle;

    userEl.className = '';
    userEl.classList.add('text-' + formattedTitle);
    userEl.style.color = '';
}

async function handleLogin() {
    if(!navigator.onLine) return showToast("You are offline.", "error");
    
    const userInput = document.getElementById('username-input');
    const errorMsg = document.getElementById('login-error');
    const btn = document.getElementById('login-btn');
    
    const user = userInput.value;
    if(!user) {
        errorMsg.innerText = "Username required.";
        return;
    }

    btn.disabled = true;
    btn.innerText = "Checking...";
    errorMsg.innerText = "";

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: user})
        });
        const data = await res.json();
        
        if(res.ok) {
            document.getElementById('display-username').innerText = user;
            updateTitleDisplay(data.title);
            
            if (data.offline) {
                showToast("⚠️ Database Offline. Playing in Temporary Mode.", "error");
            }

            document.getElementById('login-screen').classList.add('hidden');
            document.getElementById('main-screen').classList.remove('hidden');
            playClick();
        } else {
            errorMsg.innerText = data.message || "Login Failed";
        }
    } catch (e) {
        showToast("Connection Error", "error");
    } finally {
        btn.disabled = false;
        btn.innerText = "Play";
    }
}

async function setDifficulty() {
    const diff = document.getElementById('difficulty-select').value;
    try {
        const res = await fetch('/api/difficulty', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({difficulty: diff})
        });
        const data = await res.json();
        
        if(data.max_number) {
            maxNumber = data.max_number; 
            document.getElementById('guess-input').placeholder = `Guess 1 to ${maxNumber.toLocaleString()}`;
            document.getElementById('message-box').innerText = data.message;
        }
    } catch(e) { showToast("Error setting difficulty", "error"); }
    
    document.getElementById('game-interface').classList.add('hidden');
    document.getElementById('start-btn-container').classList.remove('hidden');
    document.getElementById('result-gif').style.display = 'none';
}

async function startGame() {
    if(!navigator.onLine) return;

    stopLoop();
    const btn = document.getElementById('start-btn');
    btn.disabled = true;

    try {
        const res = await fetch('/api/start', {method: 'POST'});
        const data = await res.json();
        
        document.getElementById('start-btn-container').classList.add('hidden');
        document.getElementById('game-interface').classList.remove('hidden');
        document.getElementById('message-box').innerText = data.message;
        document.getElementById('guess-history').innerText = "";
        document.getElementById('guess-input').value = "";
        document.getElementById('guess-input').focus();
        document.getElementById('result-gif').style.display = 'none';
        
        startTime = Date.now();
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            const seconds = Math.floor((Date.now() - startTime) / 1000);
            document.getElementById('timer').innerText = seconds;
        }, 1000);
        playClick();
    } catch (e) {
        showToast("Failed to start game", "error");
    } finally {
        btn.disabled = false;
    }
}

async function makeGuess() {
    if(!navigator.onLine) return;

    const input = document.getElementById('guess-input');
    const btn = document.getElementById('submit-guess-btn');
    const guessVal = input.value;
    
    if(!guessVal) return;

    btn.disabled = true;
    input.disabled = true;

    try {
        const res = await fetch('/api/guess', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({guess: guessVal})
        });

        if (res.status === 401) {
            showToast("Session expired!", "error");
            setTimeout(() => window.location.reload(), 1500);
            return;
        }

        const data = await res.json();
        if(data.status === 'warning') showToast(data.message, 'error');

        document.getElementById('message-box').innerText = data.message;
        if(data.history) document.getElementById('guess-history').innerText = data.history.join(', ');

        if (data.status === 'win') {
            endGame(true);
            updateTitleDisplay(data.new_title);
        } else if (data.status === 'lose') {
            endGame(false);
        } else {
            if(data.status !== 'warning') playClick();
            input.value = "";
            input.focus();
        }
    } catch (e) {
        showToast("Error sending guess", "error");
    } finally {
        btn.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

function endGame(won) {
    clearInterval(timerInterval);
    document.getElementById('game-interface').classList.add('hidden');
    document.getElementById('start-btn-container').classList.remove('hidden');
    
    const gif = document.getElementById('result-gif');
    gif.style.display = 'block';
    
    if(won) {
        playLoop('win'); 
        gif.src = "/static/correct.gif"; 
    } else {
        playLoop('lose'); 
        gif.src = "/static/wrong.gif";
    }
}

async function loadStats() {
    showSection('stats');
    const content = document.getElementById('stats-content');
    content.innerHTML = "Loading...";

    const res = await fetch('/api/stats');
    const data = await res.json();
    
    const winRate = data.total_games > 0 ? ((data.correct_guesses/data.total_games)*100).toFixed(1) : 0;
    
    let offlineWarning = "";
    if (data.offline) {
        offlineWarning = `<div style="color: #ff5252; margin-bottom: 15px; font-weight: bold; border: 1px solid #ff5252; padding: 10px; border-radius: 8px;">
            ⚠️ Temporary Data (Database Offline) <br> <span style="font-size:0.8em; font-weight:normal">Data will be lost when you close the browser.</span>
        </div>`;
    }

    content.innerHTML = `
        ${offlineWarning}
        <div class="stats-grid">
            <div class="stat-item"><div class="stat-val">${data.points.toLocaleString()}</div><div class="stat-label">Points</div></div>
            <div class="stat-item"><div class="stat-val">${data.total_games}</div><div class="stat-label">Games</div></div>
            <div class="stat-item"><div class="stat-val">${data.correct_guesses}</div><div class="stat-label">Wins</div></div>
            <div class="stat-item"><div class="stat-val">${winRate}%</div><div class="stat-label">Win Rate</div></div>
        </div>
    `;
}

async function loadLeaderboard() {
    showSection('leaderboard');
    const list = document.getElementById('leaderboard-list');
    list.innerHTML = "<div style='padding:20px'>Accessing Database...</div>";
    
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    
    list.innerHTML = "";
    
    if (data.error === 'db_down') {
        list.innerHTML = `
            <div style="color: #ff5252; padding: 20px; text-align: center;">
                <h3>⚠️ Cannot Load</h3>
                <p>Tell the developer to fix or make new database</p>
            </div>
        `;
        return;
    }

    data.forEach((player, index) => {
        const li = document.createElement('li');
        
        let titleHtml = '';
        let textClass = '';
        
        if (player.title) {
            const rankClass = player.title.replace(' ', '-');
            textClass = 'text-' + rankClass;
            titleHtml = `<span class="player-title title-${rankClass}"><span>${player.title}</span></span>`;
        }

        li.innerHTML = `
            <div style="display:flex; align-items:center; min-width: 0;">
                <span style="width: 30px; font-weight:bold; color: #888; flex-shrink: 0;">${index + 1}.</span>
                <div style="text-align:left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center;">
                    ${titleHtml}
                    <strong class="${textClass}" style="margin-left: 8px;">${player.username}</strong>
                </div>
            </div>
            <span class="${textClass}" style="font-weight:bold; white-space: nowrap; margin-left: auto;">${player.points.toLocaleString()} points</span>
        `;
        list.appendChild(li);
    });
}

async function handleLogout() {
    await fetch('/logout');
    location.reload();
}