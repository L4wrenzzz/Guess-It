# Guess It - FULLY VIBE CODED by 1st year IT student
Play it here: [https://guess-it-txiy.onrender.com](https://guess-it-txiy.onrender.com)

A high-performance, secure number guessing game built with Python (Flask) and Supabase. Designed to demonstrate production-grade security architecture, atomic state management, and a glassmorphism UI.

## 🏗️ Architecture

- **Hosting:** Render
- **Database:** Supabase (PostgreSQL)
- **Caching:** Redis (with fallback to memory)
- **Monitoring:** Blackfire.io Profiling

## 🚀 Features

* **Atomic State Management:** SQL-based scoring using atomic upserts (`ON CONFLICT DO UPDATE`) to prevent race conditions during high-concurrency gameplay.
* **Defense-in-Depth Security:**
    * **CSP (Content Security Policy):** Strict `script-src 'self'` prevents XSS attacks.
    * **Session Encryption:** Game state tokens (target numbers) are encrypted using Fernet (symmetric encryption) to prevent client-side tampering.
    * **Rate Limiting:** Server-side throttling (3 guesses/second) to prevent brute-force automation.
* **Dynamic Leaderboard System:**
    * **Titles:** Players earn titles (Rookie, Legend, Champion) based on points.
    * **"THE ONE":** A unique, dynamic title for the #1 player on the leaderboard.
* **Resilient Architecture:** Graceful degradation to "Offline Mode" if the database connection fails, allowing the game to continue locally.
* **Modern Frontend:** Unobtrusive JavaScript with glassmorphism UI design and responsive CSS.

## 🛠️ Tech Stack

* **Backend:** Python 3.10+, Flask, Waitress (WSGI)
* **Database:** PostgreSQL (Supabase) via PL/pgSQL RPC
* **Security:** Cryptography (Fernet), Flask-Limiter
* **Frontend:** Vanilla JS (Event Delegation Pattern), CSS3 Variables

## 💻 Local Installation

Want to run this locally? Follow these steps:

1.  **Clone the repo:**
    ```bash
    git clone [https://github.com/l4wrenzzz/guess-it.git](https://github.com/l4wrenzzz/guess-it.git)
    cd guess-it
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up Environment Variables:**
    Rename `.env.example` to `.env` and fill in your Supabase credentials.
    ```bash
    mv .env.example .env
    # Edit .env with your SUPABASE_URL and SUPABASE_KEY
    ```

4.  **Run the App:**
    ```bash
    python run.py
    ```
    The game will be available at `http://localhost:5000`.

## 🧪 Testing

This project uses `pytest` for unit testing.
```bash
pytest