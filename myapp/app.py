import os
import sqlite3
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-change-it'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Создаём папки
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# База данных
def init_db():
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  last_seen TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  from_user TEXT,
                  to_user TEXT,
                  message TEXT,
                  photo TEXT,
                  timestamp TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Активные пользователи
active_users = {}
user_sids = {}

# ==================== СТРАНИЦЫ ====================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ==================== API ====================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Не указаны имя или пароль'}), 400
    
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Пользователь уже существует'}), 400
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    c.execute("INSERT INTO users (username, password, last_seen) VALUES (?, ?, ?)",
              (username, password_hash, datetime.now()))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'username': username})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password_hash))
    user = c.fetchone()
    
    if user:
        c.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), username))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'username': username})
    
    conn.close()
    return jsonify({'error': 'Неверное имя или пароль'}), 401

@app.route('/api/users/search')
def search_users():
    query = request.args.get('q', '')
    current_user = request.args.get('current', '')
    
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    
    c.execute("SELECT username, last_seen FROM users WHERE username LIKE ? AND username != ? LIMIT 50",
              (f'%{query}%', current_user))
    users = []
    for row in c.fetchall():
        users.append({
            'username': row[0],
            'last_seen': row[1],
            'online': row[0] in active_users
        })
    
    conn.close()
    return jsonify(users)

@app.route('/api/messages/<username>')
def get_messages(username):
    current_user = request.args.get('current', '')
    
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    
    c.execute('''SELECT from_user, message, photo, timestamp 
                 FROM messages 
                 WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)
                 ORDER BY timestamp LIMIT 200''',
              (current_user, username, username, current_user))
    
    messages = []
    for row in c.fetchall():
        messages.append({
            'from': row[0],
            'message': row[1],
            'photo': row[2],
            'timestamp': row[3]
        })
    
    conn.close()
    return jsonify(messages)

@app.route('/api/upload', methods=['POST'])
def upload_photo():
    if 'photo' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    
    file = request.files['photo']
    username = request.form.get('username')
    to_user = request.form.get('to')
    
    if file.filename == '':
        return jsonify({'error': 'Пустой файл'}), 400
    
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
    filename = f"{datetime.now().timestamp()}_{username}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (from_user, to_user, photo, timestamp) VALUES (?, ?, ?, ?)",
              (username, to_user, f'/uploads/{filename}', datetime.now()))
    conn.commit()
    conn.close()
    
    socketio.emit('new_message', {
        'from': username,
        'to': to_user,
        'photo': f'/uploads/{filename}',
        'timestamp': datetime.now().isoformat()
    }, room=to_user)
    
    return jsonify({'success': True, 'photo': f'/uploads/{filename}'})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ==================== WEBSOCKET ====================

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('register_user')
def register_user(data):
    username = data.get('username')
    if username:
        active_users[username] = request.sid
        user_sids[request.sid] = username
        join_room(username)
        emit('user_status', {'username': username, 'online': True}, broadcast=True)

@socketio.on('send_message')
def handle_send_message(data):
    from_user = data.get('from')
    to_user = data.get('to')
    message = data.get('message')
    
    if not from_user or not to_user:
        return
    
    conn = sqlite3.connect('messenger.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (from_user, to_user, message, timestamp) VALUES (?, ?, ?, ?)",
              (from_user, to_user, message, datetime.now()))
    conn.commit()
    conn.close()
    
    socketio.emit('new_message', {
        'from': from_user,
        'to': to_user,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }, room=to_user)

@socketio.on('disconnect')
def handle_disconnect():
    username = user_sids.get(request.sid)
    if username:
        active_users.pop(username, None)
        user_sids.pop(request.sid, None)
        emit('user_status', {'username': username, 'online': False}, broadcast=True)

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
