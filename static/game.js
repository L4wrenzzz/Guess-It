class GameAPI {
    static async login(username) {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username})
        });
        return await res.json();
    }

    static async setDifficulty(difficulty) {
        const res = await fetch('/api/difficulty', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({difficulty})
        });
        return await res.json();
    }

    static async startGame() {
        const res = await fetch('/api/start', {method: 'POST'});
        return await res.json();
    }

    static async submitGuess(guess) {
        const res = await fetch('/api/guess', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({guess})
        });
        if (res.status === 401) {
            window.location.reload(); 
            return null;
        }
        return await res.json();
    }

    static async getStats() {
        const res = await fetch('/api/stats');
        return await res.json();
    }

    static async getLeaderboard() {
        const res = await fetch('/api/leaderboard');
        return await res.json();
    }

    static async logout() {
        await fetch('/logout');
    }
}

class UIManager {
    constructor() {
        this.dom = {
            toast: document.querySelector('.toast-msg'),
        };
        
        const config = document.getElementById('game-config');
        this.assets = {
            win: config ? config.dataset.winSound : '',
            lose: config ? config.dataset.loseSound : '',
            correctGif: config ? config.dataset.correctGif : '',
            wrongGif: config ? config.dataset.wrongGif : ''
        };
        
        this.currentAudio = null;
    }

    $(id) { return document.getElementById(id); }

    showToast(message, type = 'info') {
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

    playClick() {
        const s = document.getElementById('clickSound');
        if (s) { s.currentTime = 0; s.play().catch(()=>{}); }
    }

    playLoop(type) {
        this.stopLoop();
        const audioId = type + 'Sound'; 
        this.currentAudio = document.getElementById(audioId);
        if(this.currentAudio) {
            this.currentAudio.loop = true;
            this.currentAudio.currentTime = 0;
            this.currentAudio.play().catch(e=>{});
        }
    }

    stopLoop() {
        if(this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
    }
    
    setResultGif(won) {
        const gif = this.$('result-gif');
        gif.style.display = 'block';
        gif.src = won ? this.assets.correctGif : this.assets.wrongGif;
    }

    showSection(id) {
        ['game', 'stats', 'leaderboard', 'titles'].forEach(s => {
            const el = this.$('section-' + s);
            if (el) el.classList.add('hidden');
        });
        const active = this.$('section-' + id);
        if (active) active.classList.remove('hidden');
        this.playClick();
    }

    updateTitleDisplay(title) {
        const titleEl = this.$('display-title');
        const userEl = this.$('display-username');
    
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
}

class GameController {
    constructor() {
        this.ui = new UIManager();
        this.timerInterval = null;
        this.startTime = null;
        this.gameActive = false;
        this.bindEvents();
    }

    $(id) { return document.getElementById(id); }

    bindEvents() {
        window.addEventListener('offline', () => this.ui.showToast("⚠️ No Internet", "error"));
        window.addEventListener('online', () => this.ui.showToast("✅ Back Online", "success"));
        
        window.addEventListener('beforeunload', (e) => {
            if (this.gameActive) {
                e.preventDefault();
                return "Changes you made may not be saved.";
            }
        });

        document.addEventListener('click', () => { if(this.ui.currentAudio) this.ui.stopLoop(); });
        document.addEventListener('keydown', () => { if(this.ui.currentAudio) this.ui.stopLoop(); });

        const loginBtn = this.$('login-btn');
        if (loginBtn) loginBtn.addEventListener('click', () => this.handleLogin());

        const startBtn = this.$('start-btn');
        if (startBtn) startBtn.addEventListener('click', () => this.startGame());

        const submitBtn = this.$('submit-guess-btn');
        if (submitBtn) submitBtn.addEventListener('click', () => this.makeGuess());

        const guessInput = this.$('guess-input');
        if (guessInput) {
            guessInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this.makeGuess();
            });
        }
        
        const diffSelect = this.$('difficulty-select');
        if (diffSelect) {
            diffSelect.addEventListener('focus', () => {
                diffSelect.setAttribute('data-prev', diffSelect.value);
            });
            diffSelect.addEventListener('change', () => this.handleDifficultyChange());
        }

        const buttons = document.querySelectorAll('button.secondary');
        buttons.forEach(btn => {
            if (btn.innerText.includes('Game')) btn.addEventListener('click', () => this.ui.showSection('game'));
            if (btn.innerText.includes('Stats')) btn.addEventListener('click', () => this.loadStats());
            if (btn.innerText.includes('Leaderboard')) btn.addEventListener('click', () => this.loadLeaderboard());
            if (btn.innerText.includes('Titles')) btn.addEventListener('click', () => this.ui.showSection('titles'));
        });

        const quitBtn = document.querySelector('button.quit');
        if (quitBtn) quitBtn.addEventListener('click', () => this.handleLogout());
    }

    async handleDifficultyChange() {
        const diffSelect = this.$('difficulty-select');
        
        if (this.gameActive) {
            const confirmed = confirm("⚠️ Warning: Changing difficulty will forfeit your current game!\n\nDo you want to proceed?");
            if (!confirmed) {
                const prev = diffSelect.getAttribute('data-prev');
                if(prev) diffSelect.value = prev;
                return;
            }
        }
        await this.setDifficulty(diffSelect.value);
    }

    async handleLogin() {
        if(!navigator.onLine) return this.ui.showToast("You are offline.", "error");
        
        const username = this.$('username-input').value;
        if(!username) return;

        this.$('login-btn').disabled = true;
        this.$('login-btn').innerText = "Checking...";
        
        try {
            const data = await GameAPI.login(username);
            if(data.success) {
                this.$('display-username').innerText = username;
                this.ui.updateTitleDisplay(data.title);
                
                if (data.offline) {
                    this.ui.showToast("⚠️ Database Offline. Playing in Temporary Mode.", "error");
                }

                this.$('login-screen').classList.add('hidden');
                this.$('main-screen').classList.remove('hidden');
                this.ui.playClick();
            } else {
                this.$('login-error').innerText = data.message;
            }
        } catch (e) {
            this.ui.showToast("Connection Error", "error");
        } finally {
            this.$('login-btn').disabled = false;
            this.$('login-btn').innerText = "Play";
        }
    }

    async setDifficulty(difficultyValue) {
        const diffSelect = this.$('difficulty-select');
        const diff = difficultyValue || (diffSelect ? diffSelect.value : 'easy');
    
        try {
            const data = await GameAPI.setDifficulty(diff);
            
            if (data.forfeited) {
                this.ui.showToast("🚫 Game Forfeited", "error");
            }

            if(data.max_number) {
                this.$('guess-input').placeholder = `Guess 1 to ${data.max_number.toLocaleString()}`;
                this.$('message-box').innerText = data.message;
            }
            
            this.gameActive = false;

        } catch(e) { this.ui.showToast("Error setting difficulty", "error"); }
        
        this.$('game-interface').classList.add('hidden');
        this.$('start-btn-container').classList.remove('hidden');
        this.$('result-gif').style.display = 'none';
    }

    async startGame() {
        this.ui.stopLoop();
        this.$('start-btn').disabled = true;

        try {
            const data = await GameAPI.startGame();
            this.$('start-btn-container').classList.add('hidden');
            this.$('game-interface').classList.remove('hidden');
            this.$('message-box').innerText = data.message;
            this.$('guess-history').innerText = "";
            this.$('guess-input').value = "";
            this.$('guess-input').focus();
            this.$('result-gif').style.display = 'none';

            this.startTime = Date.now();
            clearInterval(this.timerInterval);
            this.timerInterval = setInterval(() => {
                const seconds = Math.floor((Date.now() - this.startTime) / 1000);
                this.$('timer').innerText = seconds;
            }, 1000);
            this.ui.playClick();
            
            this.gameActive = true;

        } catch (e) {
            this.ui.showToast("Failed to start", "error");
        } finally {
            this.$('start-btn').disabled = false;
        }
    }

    async makeGuess() {
        const input = this.$('guess-input');
        const val = input.value;
        if (!val) return;

        this.$('submit-guess-btn').disabled = true; 

        try {
            const data = await GameAPI.submitGuess(val);
            if (!data) return;

            if(data.status === 'warning') this.ui.showToast(data.message, 'error');
            
            this.$('message-box').innerText = data.message;
            if(data.history) this.$('guess-history').innerText = data.history.join(', ');

            if (data.status === 'win') {
                this.endGame(true);
                this.ui.updateTitleDisplay(data.new_title);
            } else if (data.status === 'lose') {
                this.endGame(false);
            } else {
                input.value = "";
                input.focus();
                if(data.status !== 'warning') this.ui.playClick();
            }
        } catch (e) {
            this.ui.showToast("Error sending guess", "error");
        } finally {
            this.$('submit-guess-btn').disabled = false;
            input.focus();
        }
    }

    endGame(won) {
        clearInterval(this.timerInterval);
        this.$('game-interface').classList.add('hidden');
        this.$('start-btn-container').classList.remove('hidden');
        
        this.ui.playLoop(won ? 'win' : 'lose');
        this.ui.setResultGif(won);
        
        this.gameActive = false;
    }

    async loadStats() {
        this.ui.showSection('stats');
        const content = this.$('stats-content');
        content.innerHTML = "Loading...";
    
        const data = await GameAPI.getStats();
        
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

    async loadLeaderboard() {
        this.ui.showSection('leaderboard');
        const list = this.$('leaderboard-list');
        list.innerHTML = "<div style='padding:20px'>Accessing Database...</div>";
        
        const data = await GameAPI.getLeaderboard();
        
        list.innerHTML = "";
        
        if (data.error === 'db_down') {
            list.innerHTML = `
                <div style="color: #ff5252; padding: 20px; text-align: center;">
                    <h3>⚠️ Cannot Load</h3>
                    <p>Database is currently offline.</p>
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

    async handleLogout() {
        if (this.gameActive) {
            const confirmed = confirm("⚠️ Warning: Logging out will forfeit your current game!\n\nDo you want to proceed?");
            if (!confirmed) return;
            this.gameActive = false;
        }
        await GameAPI.logout();
        location.reload();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new GameController();
});