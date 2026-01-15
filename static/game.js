/* Class: GameAPI
  Purpose: Handles all network requests to the Flask server.
  Uses 'async/await' for cleaner code than old-school Promises/Callbacks.
*/
class GameAPI {
    // Sends login request
    static async login(username) {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username})
        });
        return await response.json();
    }

    // Sets game difficulty
    static async setDifficulty(difficulty) {
        const response = await fetch('/api/difficulty', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({difficulty})
        });
        return await response.json();
    }

    static async startGame() {
        const response = await fetch('/api/start', {method: 'POST'});
        return await response.json();
    }

    static async submitGuess(guess) {
        const response = await fetch('/api/guess', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({guess})
        });
        // If session expired (401), reload to force login
        if (response.status === 401) {
            window.location.reload(); 
            return null;
        }
        return await response.json();
    }

    // Fetches player stats
    static async getStats() {
        const response = await fetch('/api/stats');
        return await response.json();
    }

    static async getLeaderboard() {
        const response = await fetch('/api/leaderboard');
        return await response.json();
    }

    static async logout() {
        await fetch('/logout');
    }
}

/*
  Class: UIManager
  Purpose: Handles everything related to the visual DOM (updating text, showing divs)
  and Audio playback. Decouples logic from display.
*/
class UIManager {
    constructor() {
        this.dom = {
            toast: document.querySelector('.toast-message'),
        };
        
        // Define Win/Lose asset collections
        this.assets = {
            win: [
                { sound: 'win_hakari.mp3',  gif: 'win_hakari.gif' },
                { sound: 'win_spidian.mp3', gif: 'win_spidian.gif' },
                { sound: 'win_luffy.mp3',   gif: 'win_luffy.gif' },
                { sound: 'win_wow.mp3',     gif: 'win_wow.gif' },
            ],
            lose: [
                { sound: 'lose_noob.mp3',     gif: 'lose_noob.gif' },
                { sound: 'lose_dogLaugh.mp3', gif: 'lose_dogLaugh.gif' },
                { sound: 'lose_FAH.mp3',      gif: 'lose_FAH.gif' },
                { sound: 'lose_laugh.mp3',    gif: 'lose_laugh.gif' },
            ]
        };
        
        this.currentAudio = null;
    }

    // Helper jQuery-like selector
    $(id) { return document.getElementById(id); }

    // Creates a temporary floating notification (Toast)
    showToast(message, type = 'info') {
        const existing = document.querySelector('.toast-message');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = `toast-message toast-${type}`;
        // Dynamic styling for the toast
        toast.style.cssText = `
            position: fixed; top: 20px; right: 20px; 
            background: rgba(0,0,0,0.8); color: #fff; padding: 12px 24px; 
            border-radius: 8px; z-index: 1000; animation: fadeIn 0.3s;
            border-left: 4px solid ${type === 'error' ? '#ff5252' : '#00f260'};
        `;
        toast.innerText = message;
        document.body.appendChild(toast);
        // Auto-remove after 3 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // Plays click sound effect
    playClick() {
        const soundElement = document.getElementById('clickSound');
        if (soundElement) { 
            soundElement.currentTime = 0; 
            soundElement.play().catch(()=>{}); 
        }
    }

    // --- RANDOM ASSET LOGIC ---
    triggerEndGameEffect(won) {
        this.stopLoop(); // Stop any previous sound

        // 1. Select the Collection (Win vs Lose)
        const type = won ? 'win' : 'lose';
        const collection = this.assets[type];

        // 2. Pick a Random Pair
        const randomPair = collection[Math.floor(Math.random() * collection.length)];

        // 3. Update GIF
        const gif = this.$('result-gif');
        gif.style.display = 'block';
        gif.src = '/static/' + randomPair.gif; // Points to static folder

        // 4. Update and Play Audio
        // We reuse the audio elements in HTML but change their source dynamically
        const audioId = won ? 'winSound' : 'loseSound';
        this.currentAudio = document.getElementById(audioId);
        
        if (this.currentAudio) {
            this.currentAudio.src = '/static/' + randomPair.sound; // Change source to random file
            this.currentAudio.loop = true;
            this.currentAudio.currentTime = 0;
            this.currentAudio.play().catch(error => console.log("Audio play blocked:", error));
        }
    }

    stopLoop() {
        if(this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
    }

    // Toggles visibility between Game, Stats, Leaderboard sections
    showSection(id) {
        this.stopLoop(); // Stop any playing audio loops when switching sections

        ['game', 'stats', 'leaderboard', 'titles'].forEach(sectionId => {
            const element = this.$('section-' + sectionId);
            if (element) element.classList.add('hidden');
        });
        const active = this.$('section-' + id);
        if (active) active.classList.remove('hidden');
        this.playClick();
    }

    // Updates the colored title badge next to the username
    updateTitleDisplay(title) {
        const titleElement = this.$('display-title');
        const userElement = this.$('display-username');
    
        if (!title) {
            titleElement.className = 'player-title hidden';
            titleElement.innerHTML = '';
            userElement.className = '';
            userElement.style.color = '';
            return;
        }
    
        // Show title badge
        titleElement.classList.remove('hidden');
        const formattedTitle = title.replace(' ', '-');
    
        if(title === "THE ONE") {
            titleElement.innerHTML = "<span>THE ONE</span>";
        } else {
            titleElement.innerText = title;
        }
        titleElement.className = 'player-title title-' + formattedTitle;
    
        userElement.className = '';
        userElement.classList.add('text-' + formattedTitle);
        userElement.style.color = '';
    }
}

/*
  Class: GameController
  Purpose: The "Brain" of the frontend. Connects User Actions -> API Calls -> UI Updates.
*/
class GameController {
    constructor() {
        this.ui = new UIManager();
        this.timerInterval = null;
        this.startTime = null;
        this.gameActive = false;
        this.bindEvents(); // Sets up all click listeners
    }

    $(id) { return document.getElementById(id); }

    bindEvents() {
        // Handle Internet connection loss
        window.addEventListener('offline', () => this.ui.showToast("⚠️ No Internet", "error"));
        window.addEventListener('online', () => this.ui.showToast("✅ Back Online", "success"));
        
        // Prevent accidental closing of tab during a game
        window.addEventListener('beforeunload', (event) => {
            if (this.gameActive) { event.preventDefault(); return "Changes you made may not be saved."; }
        });

        const loginButton = this.$('login-button');
        if (loginButton) loginButton.addEventListener('click', () => this.handleLogin());

        const startButton = this.$('start-button');
        if (startButton) startButton.addEventListener('click', () => this.startGame());

        const submitButton = this.$('submit-guess-button');
        if (submitButton) submitButton.addEventListener('click', () => this.makeGuess());

        // Allow pressing "Enter" to submit guess
        const guessInput = this.$('guess-input');
        if (guessInput) {
            guessInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') this.makeGuess();
            });
        }
        
        // Difficulty selector logic
        const difficultySelect = this.$('difficulty-select');
        if (difficultySelect) {
            // Save previous value in case user cancels change
            difficultySelect.addEventListener('focus', () => {
                difficultySelect.setAttribute('data-prev', difficultySelect.value);
            });
            difficultySelect.addEventListener('change', () => this.handleDifficultyChange());
        }

        // Navigation Menu Logic
        const buttons = document.querySelectorAll('button.secondary');
        buttons.forEach(button => {
            if (button.innerText.includes('Game')) button.addEventListener('click', () => this.ui.showSection('game'));
            if (button.innerText.includes('Stats')) button.addEventListener('click', () => this.loadStats());
            if (button.innerText.includes('Leaderboard')) button.addEventListener('click', () => this.loadLeaderboard());
            if (button.innerText.includes('Titles')) button.addEventListener('click', () => this.ui.showSection('titles'));
        });

        const quitButton = document.querySelector('button.quit');
        if (quitButton) quitButton.addEventListener('click', () => this.handleLogout());
    }

    // Logic to warn user if they change difficulty mid-game (causes forfeit)
    async handleDifficultyChange() {
        const difficultySelect = this.$('difficulty-select');
        
        if (this.gameActive) {
            const confirmed = confirm("⚠️ Warning: Changing difficulty will forfeit your current game!\n\nDo you want to proceed?");
            if (!confirmed) {
                const previousDifficulty = difficultySelect.getAttribute('data-prev');
                if(previousDifficulty) difficultySelect.value = previousDifficulty;
                return;
            }
        }
        await this.setDifficulty(difficultySelect.value);
    }

    async handleLogin() {
        if(!navigator.onLine) return this.ui.showToast("You are offline.", "error");
        
        const usernameInput = this.$('username-input');
        const username = usernameInput.value.trim();
        const errorText = this.$('login-error');

        // 1. Check if empty
        if (!username) {
            errorText.innerText = "Username required!";
            usernameInput.focus();
            return;
        }

        // 2. Check for symbols (Allow only letters and numbers)
        // Regex: ^ means start, [a-zA-Z0-9] means alphanumeric, + means one or more, $ means end
        if (!/^[a-zA-Z0-9]+$/.test(username)) {
            errorText.innerText = "Only letters and numbers are allowed!";
            usernameInput.focus();
            return;
        }
        
        // Clear error if valid
        errorText.innerText = "";

        // Visual feedback (disable button)
        this.$('login-button').disabled = true;
        this.$('login-button').innerText = "Checking...";
        
        try {
            const data = await GameAPI.login(username);
            if(data.success) {
                this.$('display-username').innerText = username;
                this.ui.updateTitleDisplay(data.title);
                
                if (data.offline) {
                    this.ui.showToast("⚠️ Database Offline. Playing in Temporary Mode.", "error");
                }

                // Switch screens
                this.$('login-screen').classList.add('hidden');
                this.$('main-screen').classList.remove('hidden');
                this.ui.playClick();
            } else {
                this.$('login-error').innerText = data.message;
            }
        } catch (error) {
            this.ui.showToast("Connection Error", "error");
        } finally {
            this.$('login-button').disabled = false;
            this.$('login-button').innerText = "Play";
        }
    }

    // Sets the game difficulty on the server
    async setDifficulty(difficultyValue) {
        this.ui.stopLoop(); // Stop any playing audio loops when changing difficulty

        const difficultySelect = this.$('difficulty-select');
        const diff = difficultyValue || (difficultySelect ? difficultySelect.value : 'easy');
    
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

        } catch(error) { this.ui.showToast("Error setting difficulty", "error"); }
        
        // Reset UI to "Start" state
        this.$('game-interface').classList.add('hidden');
        this.$('start-button-container').classList.remove('hidden');
        this.$('result-gif').style.display = 'none';
    }

    async startGame() {
        this.ui.stopLoop();
        this.$('start-button').disabled = true;

        try {
            const data = await GameAPI.startGame();
            // Swap "Start" button for "Game Interface"
            this.$('start-button-container').classList.add('hidden');
            this.$('game-interface').classList.remove('hidden');
            this.$('message-box').innerText = data.message;
            this.$('guess-history').innerText = "";
            this.$('guess-input').value = "";
            this.$('guess-input').focus();
            this.$('result-gif').style.display = 'none';

            // Start the client-side timer (for visual effect only)
            this.startTime = Date.now();
            clearInterval(this.timerInterval);
            this.timerInterval = setInterval(() => {
                const seconds = Math.floor((Date.now() - this.startTime) / 1000);
                this.$('timer').innerText = seconds;
            }, 1000);
            this.ui.playClick();
            
            this.gameActive = true;

        // Error starting game
        } catch (error) {
            this.ui.showToast("Failed to start", "error");
        } finally {
            this.$('start-button').disabled = false;
        }
    }

    // Handles submitting a guess to the server
    async makeGuess() {
        const input = this.$('guess-input');
        const guessValue = input.value;
        if (!guessValue) return;

        this.$('submit-guess-button').disabled = true; 

        try {
            const data = await GameAPI.submitGuess(guessValue);
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
                // Game Continues
                input.value = "";
                input.focus();
                if(data.status !== 'warning') this.ui.playClick();
            }
        } catch (error) {
            this.ui.showToast("Error sending guess", "error");
        } finally {
            this.$('submit-guess-button').disabled = false;
            input.focus();
        }
    }

    endGame(won) {
        clearInterval(this.timerInterval);
        this.$('game-interface').classList.add('hidden');
        this.$('start-button-container').classList.remove('hidden');

        this.$('start-button').innerText = "Try again";
        
        // Trigger Win/Lose effects
        this.ui.triggerEndGameEffect(won);
        
        this.gameActive = false;
    }

    // Fetches and displays player stats
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

    // Fetches and displays the global leaderboard
    async loadLeaderboard() {
        this.ui.showSection('leaderboard');
        const leaderboardList = document.getElementById('leaderboard-list');
        
        // 1. Safe Clear: Removes all previous entries safely
        leaderboardList.replaceChildren(); 
        
        const loadingMessage = document.createElement('div');
        loadingMessage.style.padding = "20px";
        loadingMessage.innerText = "Accessing Database...";
        leaderboardList.appendChild(loadingMessage);
        
        const data = await GameAPI.getLeaderboard();
        
        // Clear loading text
        leaderboardList.replaceChildren();
        
        if (data.error === 'db_down') {
            const errorDiv = document.createElement('div');
            errorDiv.style.color = "#ff5252";
            errorDiv.style.padding = "20px";
            errorDiv.style.textAlign = "center";
            errorDiv.innerHTML = "<h3>⚠️ Cannot Load</h3><p>Database is currently offline.</p>";
            leaderboardList.appendChild(errorDiv);
            return;
        }
    
        // Populate leaderboard entries safely using document.createElement
        // This prevents "HTML Injection" attacks
        data.forEach((player, index) => {
            const listItem = document.createElement('li');
            
            // Container for Rank + Name
            const leftContainer = document.createElement('div');
            leftContainer.style.display = "flex";
            leftContainer.style.alignItems = "center";
            leftContainer.style.minWidth = "0";

            // Rank Number
            const rankSpan = document.createElement('span');
            rankSpan.innerText = `${index + 1}.`;
            rankSpan.style.width = "30px";
            rankSpan.style.fontWeight = "bold";
            rankSpan.style.color = "#888";
            leftContainer.appendChild(rankSpan);

            // Name Container
            const nameContainer = document.createElement('div');
            nameContainer.style.textAlign = "left";
            nameContainer.style.display = "flex";
            nameContainer.style.alignItems = "center";

            let textClass = '';
            
            // Title Badge (if they have one)
            if (player.title) {
                const rankClass = player.title.replace(/ /g, '-');
                textClass = 'text-' + rankClass;
                
                const titleBadge = document.createElement('span');
                titleBadge.className = `player-title title-${rankClass}`;
                
                const innerTitle = document.createElement('span');
                innerTitle.innerText = player.title;
                titleBadge.appendChild(innerTitle);
                
                nameContainer.appendChild(titleBadge);
            }

            // Username (Safe Text Injection)
            const nameStrong = document.createElement('strong');
            nameStrong.innerText = player.username; 
            nameStrong.style.marginLeft = "8px";
            if (textClass) nameStrong.className = textClass;
            
            nameContainer.appendChild(nameStrong);
            leftContainer.appendChild(nameContainer);
            listItem.appendChild(leftContainer);

            // Points
            const pointsSpan = document.createElement('span');
            pointsSpan.innerText = `${player.points.toLocaleString()} points`;
            pointsSpan.style.fontWeight = "bold";
            pointsSpan.style.marginLeft = "auto";
            if (textClass) pointsSpan.className = textClass;
            listItem.appendChild(pointsSpan);

            leaderboardList.appendChild(listItem);
        });
    }

    async handleLogout() {
        // This is the prompt you were looking for:
        if (this.gameActive) {
            const confirmed = confirm("⚠️ Warning: Logging out will forfeit your current game!\n\nDo you want to proceed?");
            if (!confirmed) return;
            this.gameActive = false;
        }
        await GameAPI.logout();
        location.reload(); // Refresh page to return to login screen
    }
}

// Start the app when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    new GameController();
});