import sqlite3
import os
from datetime import datetime


def get_db_path():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'linkScanne.db')


def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_premium INTEGER DEFAULT 0,
            premium_expires_at TEXT,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_analyses (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            url TEXT NOT NULL,
            analysis_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()


def get_active_session_user_id():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id FROM sessions
        WHERE expires_at > ?
        ORDER BY created_at DESC
        LIMIT 1
    ''', (datetime.now().isoformat(),))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_by_id(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, email, is_premium, premium_expires_at FROM users WHERE id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row


def update_user_premium(user_id, is_premium, expires_at=None):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET is_premium = ?, premium_expires_at = ? WHERE id = ?',
        (1 if is_premium else 0, expires_at, user_id)
    )
    conn.commit()
    conn.close()


def set_user_premium_expired(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_premium = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()


def update_user_last_login(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()


def create_session(session_id, user_id, expires_at):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO sessions (id, user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?)
    ''', (session_id, user_id, datetime.now().isoformat(), expires_at.isoformat()))
    conn.commit()
    conn.close()


def delete_sessions_by_user(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def get_user_by_email(email):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, email, password_hash, is_premium, premium_expires_at FROM users WHERE email = ?',
        (email,)
    )
    row = cursor.fetchone()
    conn.close()
    return row


def email_exists(email):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def create_user(name, email, password_hash, created_at):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (name, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
    ''', (name[:100], email[:100], password_hash, created_at))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def save_analysis(analysis_id, user_id, url, analysis_data, created_at):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO saved_analyses (id, user_id, url, analysis_data, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (analysis_id, user_id, url, analysis_data, created_at))
    conn.commit()
    conn.close()


def get_analysis_by_id(analysis_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT analysis_data FROM saved_analyses WHERE id = ?', (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_saved_analyses_by_user(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, url, analysis_data, created_at
        FROM saved_analyses
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 100
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_analysis(analysis_id, user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM saved_analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
    if cursor.fetchone():
        cursor.execute('DELETE FROM saved_analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
        conn.commit()
        deleted = True
    else:
        deleted = False
    conn.close()
    return deleted


def get_user_profile_row(user_id):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, email, is_premium, premium_expires_at, created_at, last_login FROM users WHERE id = ?',
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def update_user_name_email(user_id, name, email):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(?) AND id != ?', (email, user_id))
    if cursor.fetchone():
        conn.close()
        return False, 'email_taken'
    cursor.execute(
        'UPDATE users SET name = ?, email = ? WHERE id = ?',
        (name[:100], email[:100].strip(), user_id),
    )
    conn.commit()
    conn.close()
    return True, None


def update_user_password_hash_by_id(user_id, password_hash):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
    conn.commit()
    conn.close()
