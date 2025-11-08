
from flask import Flask, request, redirect, jsonify, send_from_directory, render_template, abort
import mysql.connector

# Database configuration - updated to use the user's database
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '2702',
    'database': 'vairam'
}
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from werkzeug.exceptions import HTTPException
from flask_cors import CORS

# Compiled URL validation pattern (ensures URL starts with http:// or https://)
VALID_URL_PATTERN = re.compile(r'^(?:http|https)://', re.IGNORECASE)

def generate_short_code(length=6):
    """Generate a random URL-safe string of given length."""
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

app = Flask(__name__, template_folder='templates')
CORS(app)


@app.errorhandler(Exception)
def handle_error(error):
    if isinstance(error, HTTPException):
        code = error.code
        message = error.description
    else:
        code = 500
        message = "Something went wrong! Please try again."
    return (
        jsonify({'error': message, 'code': code}),
        code,
    )


def get_db():
    """Database connection factory with better error handling"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        app.logger.error(f"Database connection failed: {e}")
        if getattr(e, 'errno', None) == 2003:  # Can't connect to MySQL server
            abort(503, description="Database server is unavailable. Please try again later.")
        elif getattr(e, 'errno', None) == 1045:  # Access denied
            abort(500, description="Database configuration error. Please contact support.")
        elif getattr(e, 'errno', None) == 1049:  # Unknown database
            abort(500, description="Database not found. Please contact support.")
        raise


@app.route('/', methods=['GET'])
def index():
    return render_template('a.html')


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

        # Ensure table exists (simple bootstrap)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS urls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                long_url TEXT NOT NULL,
                short_code VARCHAR(191) NOT NULL UNIQUE,
                custom_path VARCHAR(191) DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME DEFAULT NULL,
                password_hash VARCHAR(255) DEFAULT NULL,
                is_private BOOLEAN DEFAULT FALSE,
                click_count INT DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        conn.commit()

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
            for attempt in range(10):
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
        cursor.execute(
            """
            INSERT INTO urls (
                long_url, short_code, expires_at, password_hash,
                is_private, custom_path
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                long_url, short_code, expires_at, password_hash,
                False, custom_alias
            )
        )
        conn.commit()

        # Prepare response
        short_url = request.host_url.rstrip('/') + '/' + short_code
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


@app.route('/<short_code>')
def redirect_short(short_code):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT long_url, expires_at, password_hash, click_count FROM urls WHERE short_code = %s OR custom_path = %s", (short_code, short_code))
        row = cursor.fetchone()
        if not row:
            abort(404, description='Short link not found')
        if row.get('expires_at') and row['expires_at'] < datetime.utcnow():
            abort(410, description='This short link has expired')

        # increment click count
        cursor.execute("UPDATE urls SET click_count = click_count + 1 WHERE short_code = %s", (short_code,))
        conn.commit()

        return redirect(row['long_url'], code=302)

    except mysql.connector.Error as e:
        app.logger.error(f"Database error in redirect: {e}")
        abort(500, description='Server error')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == '__main__':
    # Run the app on port 3000 so it matches previously used client URLs
    app.run(host='0.0.0.0', port=3000, debug=True)
