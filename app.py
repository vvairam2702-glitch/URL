# Add these imports at the top of app.py
from flask import Flask, request, redirect, jsonify, send_from_directory, render_template_string, abort
import mysql.connector

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '2702',
    'database': 'test'
}
import hashlib
import os
import secrets
import re
from datetime import datetime, timedelta
from werkzeug.exceptions import HTTPException

# Compiled URL validation pattern (ensures URL starts with http:// or https://)
VALID_URL_PATTERN = re.compile(r'^(?:http|https)://', re.IGNORECASE)

def generate_short_code(length=6):
    """Generate a random URL-safe string of given length."""
    return ''.join(secrets.choice('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
                  for _ in range(length))

app = Flask(__name__, static_folder='')

# Add this error handler right after app creation
@app.errorhandler(Exception)
def handle_error(error):
    if isinstance(error, HTTPException):
        code = error.code
        message = error.description
    else:
        code = 500
        message = "Something went wrong! Please try again."
    
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error {{ code }}</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {
                    background: linear-gradient(135deg, #2d0f42 0%, #1a082b 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                }
                .error-card {
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 15px;
                    padding: 2rem;
                    text-align: center;
                    max-width: 500px;
                    width: 90%;
                }
                .error-code {
                    font-size: 4rem;
                    font-weight: bold;
                    margin-bottom: 1rem;
                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                    -webkit-background-clip: text;
                    background-clip: text;
                    color: transparent;
                }
                .btn-home {
                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                    border: none;
                    padding: 0.5rem 2rem;
                    margin-top: 1rem;
                }
                .btn-home:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                }
            </style>
        </head>
        <body>
            <div class="error-card">
                <div class="error-code">{{ code }}</div>
                <h2>{{ message }}</h2>
                <p class="text-muted">{{ detail if detail else "" }}</p>
                <a href="/" class="btn btn-primary btn-home">Go Home</a>
            </div>
        </body>
        </html>
    """, code=code, message=message, detail=str(error) if app.debug else "")

# Modify get_db() to handle connection errors better
def get_db():
    """Database connection factory with better error handling"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        app.logger.error(f"Database connection failed: {e}")
        if e.errno == 2003:  # Can't connect to MySQL server
            abort(503, description="Database server is unavailable. Please try again later.")
        elif e.errno == 1045:  # Access denied
            abort(500, description="Database configuration error. Please contact support.")
        elif e.errno == 1049:  # Unknown database
            abort(500, description="Database not found. Please contact support.")
        raise

# Replace the error handling in shorten_url() with this:
@app.route('/shorten', methods=['POST'])
def shorten_url():
    """Handle URL shortening requests from the form"""
    # Get form data
    long_url = request.form.get('url')
    custom_alias = request.form.get('custom_alias')
    expiry_days = request.form.get('expiry_days', type=int)
    password = request.form.get('password')
    track_clicks = request.form.get('trackClicks') == 'true'
    generate_qr = request.form.get('generateQR') == 'true'

    # Validate URL
    if not long_url:
        return jsonify({'error': 'URL is required'}), 400
    if not VALID_URL_PATTERN.match(long_url):
        return jsonify({'error': 'Invalid URL format. Make sure it starts with http:// or https://'}), 400

    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Handle custom alias
        if custom_alias:
            if len(custom_alias) > 50:
                return jsonify({'error': 'Custom alias is too long (max 50 characters)'}), 400
            if not re.match(r'^[A-Za-z0-9_-]+$', custom_alias):
                return jsonify({'error': 'Custom alias can only contain letters, numbers, hyphens and underscores'}), 400
            cursor.execute("SELECT id FROM urls WHERE custom_path = %s", (custom_alias,))
            if cursor.fetchone():
                return jsonify({'error': 'This custom alias is already taken. Please choose another.'}), 400
            short_code = custom_alias
        else:
            # Generate unique short code
            for attempt in range(5):
                short_code = generate_short_code()
                cursor.execute("SELECT id FROM urls WHERE short_code = %s", (short_code,))
                if not cursor.fetchone():
                    break
            else:
                return jsonify({'error': 'Could not generate unique short code. Please try again.'}), 500

        # Calculate expiration
        expires_at = None
        if expiry_days:
            if not 0 < expiry_days <= 365:
                return jsonify({'error': 'Expiry days must be between 1 and 365'}), 400
            expires_at = datetime.utcnow() + timedelta(days=expiry_days)

        # Hash password if provided
        password_hash = None
        if password:
            if len(password) < 4:
                return jsonify({'error': 'Password must be at least 4 characters long'}), 400
            password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Insert URL
        cursor.execute("""
            INSERT INTO urls (
                long_url, short_code, expires_at, password_hash,
                is_private, custom_path
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            long_url, short_code, expires_at, password_hash,
            False, custom_alias
        ))
        conn.commit()

        # Prepare response
        short_url = request.host_url + short_code
        response_data = {
            'short_url': short_url,
            'long_url': long_url,
            'created_date': datetime.utcnow().isoformat(),
            'expiry_date': expires_at.isoformat() if expires_at else None,
            'click_count': 0
        }

        return jsonify(response_data), 201

    except mysql.connector.Error as e:
        if conn:
            conn.rollback()
        app.logger.error(f"Database error in shorten_url: {e}")
        return jsonify({'error': 'Unable to create short URL. Please try again later.'}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()