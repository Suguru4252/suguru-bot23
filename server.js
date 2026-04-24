const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

// Раздача статических файлов
app.use(express.static(path.join(__dirname)));

// Хранилище лобби
const lobbies = new Map();

// Генерация ID лобби
function generateLobbyId() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let result = '';
    for (let i = 0; i < 6; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

io.on('connection', (socket) => {
    console.log(`Игрок подключился: ${socket.id}`);

    let currentLobby = null;
    let playerName = null;

    // Запрос списка лобби
    socket.on('request-lobbies', () => {
        const lobbiesList = [];
        lobbies.forEach((lobby, id) => {
            if (!lobby.isPrivate || lobby.password === null) {
                lobbiesList.push({
                    id: id,
                    name: lobby.name,
                    playerCount: lobby.players.length,
                    maxPlayers: lobby.maxPlayers,
                    isPrivate: lobby.isPrivate,
                    hasPassword: lobby.password !== null
                });
            }
        });
        socket.emit('lobbies-list', lobbiesList);
    });

    // Создание лобби
    socket.on('create-lobby', (data) => {
        const { name, maxPlayers, password } = data;
        const lobbyId = generateLobbyId();
        
        const lobby = {
            id: lobbyId,
            name: name || 'Лобби',
            maxPlayers: maxPlayers || 10,
            password: password || null,
            isPrivate: password ? true : false,
            players: [],
            messages: []
        };

        lobbies.set(lobbyId, lobby);
        
        // Присоединяем создателя
        lobby.players.push({
            id: socket.id,
            name: playerName || 'Игрок',
            isHost: true
        });
        
        socket.join(lobbyId);
        currentLobby = lobbyId;

        socket.emit('lobby-created', {
            id: lobbyId,
            name: lobby.name,
            maxPlayers: lobby.maxPlayers,
            hasPassword: lobby.password !== null
        });

        updateLobbyPlayers(lobbyId);
        broadcastLobbiesUpdate();
        console.log(`Лобби создано: ${lobbyId} (${lobby.name})`);
    });

    // Присоединение к лобби
    socket.on('join-lobby', (data) => {
        const { lobbyId, password, name } = data;
        const lobby = lobbies.get(lobbyId);

        if (!lobby) {
            socket.emit('join-error', 'Лобби не найдено');
            return;
        }

        if (lobby.players.length >= lobby.maxPlayers) {
            socket.emit('join-error', 'Лобби заполнено');
            return;
        }

        if (lobby.password && lobby.password !== password) {
            socket.emit('join-error', 'Неверный пароль');
            return;
        }

        // Покидаем текущее лобби если есть
        if (currentLobby) {
            leaveCurrentLobby(socket);
        }

        playerName = name || 'Игрок';
        
        lobby.players.push({
            id: socket.id,
            name: playerName,
            isHost: false
        });

        socket.join(lobbyId);
        currentLobby = lobbyId;

        // Отправляем историю сообщений
        socket.emit('message-history', lobby.messages.slice(-50));
        
        // Системное сообщение
        const systemMsg = {
            sender: 'Система',
            text: `${playerName} присоединился к лобби`,
            time: new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }),
            type: 'system'
        };
        lobby.messages.push(systemMsg);
        io.to(lobbyId).emit('new-message', systemMsg);

        socket.emit('join-success', {
            id: lobbyId,
            name: lobby.name,
            players: lobby.players.map(p => ({ name: p.name, isHost: p.isHost }))
        });

        updateLobbyPlayers(lobbyId);
        broadcastLobbiesUpdate();
    });

    // Отправка сообщения
    socket.on('send-message', (text) => {
        if (!currentLobby) return;
        
        const lobby = lobbies.get(currentLobby);
        if (!lobby) return;

        const player = lobby.players.find(p => p.id === socket.id);
        if (!player) return;

        const message = {
            sender: player.name,
            text: text,
            time: new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }),
            type: 'user'
        };

        lobby.messages.push(message);
        
        // Храним только последние 200 сообщений
        if (lobby.messages.length > 200) {
            lobby.messages = lobby.messages.slice(-200);
        }

        io.to(currentLobby).emit('new-message', message);
    });

    // Покинуть лобби
    socket.on('leave-lobby', () => {
        leaveCurrentLobby(socket);
    });

    function leaveCurrentLobby(socket) {
        if (!currentLobby) return;
        
        const lobby = lobbies.get(currentLobby);
        if (!lobby) {
            currentLobby = null;
            return;
        }

        const player = lobby.players.find(p => p.id === socket.id);
        const playerName = player ? player.name : 'Игрок';

        lobby.players = lobby.players.filter(p => p.id !== socket.id);
        socket.leave(currentLobby);

        if (lobby.players.length === 0) {
            // Удаляем пустое лобби через 30 секунд
            setTimeout(() => {
                const checkLobby = lobbies.get(currentLobby);
                if (checkLobby && checkLobby.players.length === 0) {
                    lobbies.delete(currentLobby);
                    broadcastLobbiesUpdate();
                    console.log(`Лобби удалено: ${currentLobby}`);
                }
            }, 30000);
        } else {
            // Передаём хоста если ушёл хост
            if (player && player.isHost) {
                lobby.players[0].isHost = true;
            }

            const leaveMsg = {
                sender: 'Система',
                text: `${playerName} покинул лобби`,
                time: new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }),
                type: 'system'
            };
            lobby.messages.push(leaveMsg);
            io.to(currentLobby).emit('new-message', leaveMsg);
        }

        currentLobby = null;
        socket.emit('left-lobby');
        updateLobbyPlayers(lobby.id);
        broadcastLobbiesUpdate();
    }

    // Обновление списка игроков в лобби
    function updateLobbyPlayers(lobbyId) {
        const lobby = lobbies.get(lobbyId);
        if (!lobby) return;
        
        io.to(lobbyId).emit('players-update', 
            lobby.players.map(p => ({ name: p.name, isHost: p.isHost }))
        );
    }

    // Рассылка обновлённого списка лобби всем
    function broadcastLobbiesUpdate() {
        const lobbiesList = [];
        lobbies.forEach((lobby, id) => {
            if (lobby.players.length > 0) {
                lobbiesList.push({
                    id: id,
                    name: lobby.name,
                    playerCount: lobby.players.length,
                    maxPlayers: lobby.maxPlayers,
                    hasPassword: lobby.password !== null
                });
            }
        });
        io.emit('lobbies-list', lobbiesList);
    }

    // Отключение игрока
    socket.on('disconnect', () => {
        console.log(`Игрок отключился: ${socket.id}`);
        leaveCurrentLobby(socket);
    });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`Chugur сервер запущен на порту ${PORT}`);
    console.log(`Открой http://localhost:${PORT} в браузере`);
});
