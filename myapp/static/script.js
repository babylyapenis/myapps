let socket = null;
let currentUser = null;
let currentChat = null;

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('login-btn').onclick = () => login();
    document.getElementById('register-btn').onclick = () => register();
    document.getElementById('send-btn').onclick = () => sendMessage();
    document.getElementById('message-input').onkeypress = (e) => {
        if (e.key === 'Enter') sendMessage();
    };
    document.getElementById('search-input').oninput = () => searchUsers();
    document.getElementById('photo-upload').onchange = (e) => uploadPhoto(e.target.files[0]);
});

async function login() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    
    const response = await fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, password})
    });
    
    if (response.ok) {
        currentUser = username;
        initSocket();
        document.getElementById('login-screen').style.display = 'none';
        document.getElementById('chat-screen').style.display = 'flex';
        document.getElementById('current-username').innerText = username;
        loadUsers();
    } else {
        alert('Неверное имя или пароль');
    }
}

async function register() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    
    const response = await fetch('/api/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, password})
    });
    
    if (response.ok) {
        alert('Регистрация успешна! Теперь войдите.');
    } else {
        alert('Пользователь уже существует');
    }
}

function initSocket() {
    socket = io();
    
    socket.on('connect', () => {
        socket.emit('register_user', {username: currentUser});
    });
    
    socket.on('new_message', (data) => {
        if (currentChat === data.from || currentChat === data.to) {
            addMessageToChat(data);
        }
        loadUsers();
    });
    
    socket.on('user_status', () => {
        loadUsers();
    });
}

async function loadUsers() {
    const response = await fetch('/api/users/search?q=&current=' + currentUser);
    const users = await response.json();
    renderUsersList(users);
}

async function searchUsers() {
    const query = document.getElementById('search-input').value;
    const response = await fetch(`/api/users/search?q=${query}&current=${currentUser}`);
    const users = await response.json();
    renderUsersList(users);
}

function renderUsersList(users) {
    const container = document.getElementById('users-list');
    container.innerHTML = '';
    
    users.forEach(user => {
        const div = document.createElement('div');
        div.className = 'user-item' + (currentChat === user.username ? ' active' : '');
        div.onclick = () => openChat(user.username);
        
        div.innerHTML = `
            <div class="user-avatar">${user.username[0].toUpperCase()}</div>
            <div class="user-info-text">
                <div class="user-name">${user.username}</div>
                <div class="user-status ${user.online ? 'online' : ''}">
                    ${user.online ? 'онлайн' : 'офлайн'}
                </div>
            </div>
        `;
        container.appendChild(div);
    });
}

async function openChat(username) {
    currentChat = username;
    document.getElementById('chat-header').innerHTML = `<span>${username}</span>`;
    document.getElementById('input-area').style.display = 'block';
    
    const response = await fetch(`/api/messages/${username}?current=${currentUser}`);
    const messages = await response.json();
    
    const container = document.getElementById('messages');
    container.innerHTML = '';
    
    messages.forEach(msg => {
        addMessageToChat(msg);
    });
    
    document.querySelectorAll('.user-item').forEach(el => {
        el.classList.remove('active');
        if (el.innerText.includes(username)) el.classList.add('active');
    });
    
    container.scrollTop = container.scrollHeight;
}

function addMessageToChat(msg) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${msg.from === currentUser ? 'outgoing' : 'incoming'}`;
    
    if (msg.photo) {
        div.innerHTML = `
            <img src="${msg.photo}" class="message-photo" onclick="window.open('${msg.photo}')">
            <div class="message-time">${new Date(msg.timestamp).toLocaleTimeString()}</div>
        `;
    } else {
        div.innerHTML = `
            ${msg.message}
            <div class="message-time">${new Date(msg.timestamp).toLocaleTimeString()}</div>
        `;
    }
    
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!message || !currentChat) return;
    
    socket.emit('send_message', {
        from: currentUser,
        to: currentChat,
        message: message
    });
    
    input.value = '';
}

async function uploadPhoto(file) {
    if (!file || !currentChat) return;
    
    const formData = new FormData();
    formData.append('photo', file);
    formData.append('username', currentUser);
    formData.append('to', currentChat);
    
    await fetch('/api/upload', {
        method: 'POST',
        body: formData
    });
}
