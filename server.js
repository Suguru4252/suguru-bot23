const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
    cors: { origin: "*" },
    transports: ['websocket', 'polling']
});

app.use(express.static(path.join(__dirname)));

let players = {};

io.on('connection', (socket) => {
    console.log('✅ Игрок подключился:', socket.id);
    
    socket.on('newPlayer', (data) => {
        players[socket.id] = {
            id: socket.id,
            nickname: data.nickname || 'Герой',
            x: data.x || 1100,
            y: data.y || 900,
            classType: data.classType || 'warrior',
            level: data.level || 1,
            hp: data.hp || 320,
            maxHp: data.maxHp || 320,
            gold: data.gold || 450
        };
        socket.emit('allPlayers', players);
        socket.broadcast.emit('newPlayer', players[socket.id]);
        console.log('👥 Всего игроков:', Object.keys(players).length);
    });
    
    socket.on('updatePosition', (data) => {
        if (players[socket.id]) {
            players[socket.id].x = data.x;
            players[socket.id].y = data.y;
            players[socket.id].classType = data.classType;
            socket.broadcast.emit('playerMoved', {
                id: socket.id,
                x: data.x,
                y: data.y,
                classType: data.classType
            });
        }
    });
    
    socket.on('updateStats', (data) => {
        if (players[socket.id]) {
            players[socket.id].hp = data.hp;
            players[socket.id].maxHp = data.maxHp;
            players[socket.id].level = data.level;
            players[socket.id].gold = data.gold;
            socket.broadcast.emit('playerStatsUpdated', {
                id: socket.id,
                hp: data.hp,
                maxHp: data.maxHp,
                level: data.level
            });
        }
    });
    
    socket.on('attackPlayer', (data) => {
        const targetSocket = io.sockets.sockets.get(data.targetId);
        if (targetSocket) {
            targetSocket.emit('attacked', {
                attackerId: socket.id,
                damage: data.damage,
                attackerName: data.attackerName
            });
        }
    });
    
    socket.on('disconnect', () => {
        console.log('❌ Игрок отключился:', socket.id);
        delete players[socket.id];
        io.emit('playerLeft', socket.id);
    });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`\n🚀 СЕРВЕР ЗАПУЩЕН!`);
    console.log(`📱 Откройте в браузере: http://localhost:${PORT}`);
    console.log(`🌐 Для подключения других игроков используйте ваш IP-адрес\n`);
});
