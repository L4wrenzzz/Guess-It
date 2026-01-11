# Guess It - FULLY FIBE CODED by 1st year IT student

A high-performance, secure number guessing game built with Python (Flask) and Supabase.
Designed to demonstrate production-grade security architecture and atomic state management.

## 🚀 Features

* **Atomic State Management:** SQL-based scoring using atomic upserts (`ON CONFLICT DO UPDATE`) to prevent race conditions.
* **Defense-in-Depth Security:**
    * **CSP (Content Security Policy):** Strict `script-src 'self'` prevents XSS attacks.
    * **Session Encryption:** Game state tokens are encrypted using Fernet (symmetric encryption) to prevent client-side tampering/cheating.
    * **Rate Limiting:** Server-side 300ms cooldown enforcement.
* **Resilient Architecture:** Graceful degradation to "Offline Mode" if the database connection fails.
* **Modern Frontend:** Unobtrusive JavaScript with glassmorphism UI design.

## 🛠️ Tech Stack

* **Backend:** Python 3.10+, Flask, Waitress (WSGI)
* **Database:** PostgreSQL (Supabase) via PL/pgSQL RPC
* **Security:** Cryptography (Fernet/PBKDF2), Werkzeug
* **Frontend:** Vanilla JS (Event Delegation Pattern), CSS3 Variables

*Built with ❤️ by Lawrenzzz*