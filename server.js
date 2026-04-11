const express = require('express');
const http = require('http');
const https = require('https');
const fs = require('fs');
const { Server } = require('socket.io');
const path = require('path');
const { spawn } = require('child_process');

const app = express();

let server;
// ── Create HTTP or HTTPS server based on certs ─────────────────────────────
if (fs.existsSync('key.pem') && fs.existsSync('cert.pem')) {
  server = https.createServer({ key: fs.readFileSync('key.pem'), cert: fs.readFileSync('cert.pem') }, app);
} else {
  server = http.createServer(app);
}

const io = new Server(server, {
  cors: { origin: '*' },
  maxHttpBufferSize: 5 * 1024 * 1024, // 5MB for frame data
});

app.use(express.static(path.join(__dirname, 'public')));

// ── SPA Fallback Route ─────────────────────────────────────────────────────
// If a user requests a route that isn't a file in the static folder, 
// send them the index.html file so the frontend router can take over.
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ── State ──────────────────────────────────────────────────────────────────
const rooms = {}; // roomId → { hostId, utilisers: Set }

// ── FFmpeg V4L2 virtual camera pipe (utiliser-side, local only) ───────────
let ffmpegProc = null;
let virtualCamActive = false;
const VIRTUAL_CAM_DEVICE = process.env.VCAM_DEVICE || '/dev/video42';

function startVirtualCam(width, height) {
  if (ffmpegProc) return;
  try {
    ffmpegProc = spawn('ffmpeg', [
      '-loglevel', 'error',
      '-f', 'rawvideo',
      '-pixel_format', 'bgr24',
      '-video_size', `${width}x${height}`,
      '-framerate', '30',
      '-i', 'pipe:0',
      '-pix_fmt', 'yuyv422',
      '-f', 'v4l2',
      VIRTUAL_CAM_DEVICE,
    ], { stdio: ['pipe', 'ignore', 'inherit'] });

    // Prevent EPIPE errors from crashing the Node server
    ffmpegProc.stdin.on('error', (e) => {
      if (e.code !== 'EPIPE') console.warn('[vcam] stdin error:', e.message);
    });

    ffmpegProc.on('error', (e) => {
      console.warn('[vcam] FFmpeg error:', e.message);
      ffmpegProc = null;
      virtualCamActive = false;
    });
    ffmpegProc.on('exit', () => {
      ffmpegProc = null;
      virtualCamActive = false;
      console.log('[vcam] FFmpeg exited');
    });

    virtualCamActive = true;
    console.log(`[vcam] Streaming to ${VIRTUAL_CAM_DEVICE} at ${width}x${height}`);
  } catch (e) {
    console.warn('[vcam] Could not start FFmpeg:', e.message);
  }
}

function stopVirtualCam() {
  if (ffmpegProc) {
    ffmpegProc.kill('SIGTERM');
    ffmpegProc = null;
    virtualCamActive = false;
    console.log('[vcam] Stopped');
  }
}

// ── Socket.IO ──────────────────────────────────────────────────────────────
io.on('connection', (socket) => {
  console.log(`[+] ${socket.id} connected`);

  // ── Host joins a room ──────────────────────────────────────────────────
  socket.on('host:join', ({ roomId }) => {
    if (rooms[roomId]) {
      socket.emit('error', { message: 'Room already has a host.' });
      return;
    }
    rooms[roomId] = { hostId: socket.id, utilisers: new Set() };
    socket.join(roomId);
    socket.data.role = 'host';
    socket.data.roomId = roomId;
    console.log(`[host] ${socket.id} hosting room "${roomId}"`);
    socket.emit('host:ready', { roomId });
    io.emit('rooms:update', getRoomList());
  });

  // ── Utiliser joins a room ──────────────────────────────────────────────
  socket.on('utiliser:join', ({ roomId }) => {
    const room = rooms[roomId];
    if (!room) {
      socket.emit('error', { message: 'Room not found.' });
      return;
    }
    room.utilisers.add(socket.id);
    socket.join(roomId);
    socket.data.role = 'utiliser';
    socket.data.roomId = roomId;
    console.log(`[utiliser] ${socket.id} joined room "${roomId}"`);

    // Tell host a new utiliser wants to connect
    io.to(room.hostId).emit('utiliser:request', { utiliserId: socket.id });
    socket.emit('utiliser:waiting', { hostId: room.hostId });
    io.emit('rooms:update', getRoomList());
  });

  // ── WebRTC signaling relay ─────────────────────────────────────────────
  socket.on('rtc:offer', ({ to, offer }) => {
    io.to(to).emit('rtc:offer', { from: socket.id, offer });
  });

  socket.on('rtc:answer', ({ to, answer }) => {
    io.to(to).emit('rtc:answer', { from: socket.id, answer });
  });

  socket.on('rtc:ice', ({ to, candidate }) => {
    io.to(to).emit('rtc:ice', { from: socket.id, candidate });
  });

  // ── Virtual camera frame pipe (raw BGR24 from utiliser browser) ────────
  socket.on('vcam:frame', (frameBuffer) => {
    if (!virtualCamActive || !ffmpegProc?.stdin?.writable) return;
    try {
      ffmpegProc.stdin.write(Buffer.from(frameBuffer));
    } catch {}
  });

  socket.on('vcam:start', (opts) => {
    const w = opts?.width || parseInt(process.env.VCAM_WIDTH || '1280');
    const h = opts?.height || parseInt(process.env.VCAM_HEIGHT || '720');
    if (!virtualCamActive) startVirtualCam(w, h);
    socket.emit('vcam:status', { active: virtualCamActive, device: VIRTUAL_CAM_DEVICE });
  });

  socket.on('vcam:stop', () => {
    stopVirtualCam();
    socket.emit('vcam:status', { active: false });
  });

  socket.on('vcam:status:get', () => {
    socket.emit('vcam:status', { active: virtualCamActive, device: VIRTUAL_CAM_DEVICE });
  });

  // ── Room list ──────────────────────────────────────────────────────────
  socket.on('rooms:list', () => {
    socket.emit('rooms:update', getRoomList());
  });

  // ── Disconnect ─────────────────────────────────────────────────────────
  socket.on('disconnect', () => {
    const { role, roomId } = socket.data;
    if (!roomId || !rooms[roomId]) return;

    const room = rooms[roomId];
    if (role === 'host') {
      // Notify all utilisers
      io.to(roomId).emit('host:left', { roomId });
      delete rooms[roomId];
    } else if (role === 'utiliser') {
      room.utilisers.delete(socket.id);
      io.to(room.hostId).emit('utiliser:left', { utiliserId: socket.id });
    }
    io.emit('rooms:update', getRoomList());
    console.log(`[-] ${socket.id} (${role}) disconnected`);
  });
});

function getRoomList() {
  return Object.entries(rooms).map(([id, r]) => ({
    id,
    utilisers: r.utilisers.size,
  }));
}

// ── Start ──────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
server.listen(PORT, '0.0.0.0', () => {
  console.log(`\n✦ CamShare server running`);
  if (server instanceof https.Server) {
    console.log(`  Local:   https://localhost:${PORT}`);
    console.log(`  Network: https://<your-ip>:${PORT}`);
  } else {
    console.log(`  Local:   http://localhost:${PORT}`);
    console.log(`  Network: http://<your-ip>:${PORT}  (⚠️ Camera access requires HTTPS on LAN)`);
  }
  console.log(`\n  Virtual cam device: ${VIRTUAL_CAM_DEVICE}`);
  console.log(`  Resolution: Dynamic (Matches Host)\n`);
});

process.on('SIGINT', () => { stopVirtualCam(); process.exit(0); });
process.on('SIGTERM', () => { stopVirtualCam(); process.exit(0); });
