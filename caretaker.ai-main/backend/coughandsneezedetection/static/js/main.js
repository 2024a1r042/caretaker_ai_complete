/**
 * main.js — SonicGuard Real-Time Audio Classification Dashboard  (v2)
 *
 * v2 improvements:
 *   • 500ms chunk window (was 1s) → 2× faster feedback
 *   • Reset button clears all UI state + server buffer
 *   • Smoother animations, better visual feedback
 *   • Empty-state management for sidebar
 */

// ── Socket.IO ──────────────────────────────────────────────────────
const socket = io({
    transports: ['websocket'],
    upgrade: false
});

// Get recipient ID from URL parameters
const urlParams = new URLSearchParams(window.location.search);
const recipientId = urlParams.get('recipient_id');
const recipientName = urlParams.get('name');

// Send authentication token for database logging
socket.on('connect', () => {
    const token = localStorage.getItem('token');
    if (token) {
        socket.emit('authenticate', {
            token: token,
            recipient_id: recipientId ? parseInt(recipientId) : null
        });
    }

    // Update UI if recipient name is provided
    if (recipientName) {
        const header = document.querySelector('.header-left .logo');
        if (header) {
            header.innerHTML = `⚡ SonicGuard <span style="font-size: 0.85em; opacity: 0.7;">— ${recipientName}</span>`;
        }
    }
});

// ── DOM refs ───────────────────────────────────────────────────────
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");
const btnReset = document.getElementById("btn-reset");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const waveCanvas = document.getElementById("waveform-canvas");
const spectroCanvas = document.getElementById("spectrogram-canvas");
const alertList = document.getElementById("alert-list");
const btnClearLogs = document.getElementById("btn-clear-logs");
const alertCount = document.getElementById("alert-count");
const emptyAlerts = document.getElementById("empty-alerts");

// Class confidence bars & values
const coughBar = document.getElementById("bar-cough");
const sneezeBar = document.getElementById("bar-sneeze");
const talkingBar = document.getElementById("bar-talking");
const noiseBar = document.getElementById("bar-noise");
const coughVal = document.getElementById("val-cough");
const sneezeVal = document.getElementById("val-sneeze");
const talkingVal = document.getElementById("val-talking");
const noiseVal = document.getElementById("val-noise");
const predLabel = document.getElementById("predicted-label");
const predConf = document.getElementById("predicted-conf");
const predIcon = document.getElementById("predicted-icon");

// Stats counters
const statCough = document.getElementById("stat-cough");
const statSneeze = document.getElementById("stat-sneeze");
const statTotal = document.getElementById("stat-total");

// ── State ──────────────────────────────────────────────────────────
let audioCtx = null;
let workletNode = null;
let sourceNode = null;
let analyserNode = null;
let stream = null;
let isMonitoring = false;
let totalAlerts = 0;
let coughCount = 0;
let sneezeCount = 0;
let animFrameId = null;
let spectroFrameId = null;

const TARGET_SR = 16000;
const CHUNK_MS = 500;                       // 500ms windows
const CHUNK_SAMPLES = TARGET_SR * CHUNK_MS / 1000;  // 8000 samples
const OVERLAP = 0.5;
let nativeSR = 44100;
let pcmBuffer = [];

const SPECTRO_COLS = 200;
let spectroHistory = [];

// ── Helpers ────────────────────────────────────────────────────────
function downsample(buffer, fromRate, toRate) {
    if (fromRate === toRate) return buffer;
    const ratio = fromRate / toRate;
    const newLen = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
        result[i] = buffer[Math.min(Math.round(i * ratio), buffer.length - 1)];
    }
    return result;
}

function timestamp() {
    return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function classIcon(cls) {
    switch (cls) {
        case "Cough": return "🫁";
        case "Sneeze": return "🤧";
        case "Talking": return "🗣️";
        case "Noise": return "🔇";
        default: return "🎙️";
    }
}

// ── Waveform Drawing ───────────────────────────────────────────────
function drawWaveform() {
    if (!analyserNode || !isMonitoring) return;

    const ctx = waveCanvas.getContext("2d");
    const W = waveCanvas.width;
    const H = waveCanvas.height;
    const bufLen = analyserNode.fftSize;
    const data = new Float32Array(bufLen);
    analyserNode.getFloatTimeDomainData(data);

    ctx.clearRect(0, 0, W, H);

    // Centre line
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, H / 2);
    ctx.lineTo(W, H / 2);
    ctx.stroke();

    // Waveform gradient
    const grad = ctx.createLinearGradient(0, 0, W, 0);
    grad.addColorStop(0, "#00f0ff");
    grad.addColorStop(0.5, "#7b61ff");
    grad.addColorStop(1, "#ff4d6d");
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.beginPath();

    const sliceW = W / bufLen;
    for (let i = 0; i < bufLen; i++) {
        const y = (data[i] + 1) / 2 * H;
        if (i === 0) ctx.moveTo(0, y);
        else ctx.lineTo(i * sliceW, y);
    }
    ctx.stroke();

    // Glow effect
    ctx.globalAlpha = 0.15;
    ctx.lineWidth = 6;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.lineWidth = 2.5;

    animFrameId = requestAnimationFrame(drawWaveform);
}

// ── Spectrogram Drawing ────────────────────────────────────────────
function drawSpectrogram() {
    if (!analyserNode || !isMonitoring) return;

    const ctx = spectroCanvas.getContext("2d");
    const W = spectroCanvas.width;
    const H = spectroCanvas.height;
    const bins = analyserNode.frequencyBinCount;
    const data = new Uint8Array(bins);
    analyserNode.getByteFrequencyData(data);

    spectroHistory.push(data.slice());
    if (spectroHistory.length > SPECTRO_COLS) spectroHistory.shift();

    ctx.clearRect(0, 0, W, H);
    const colW = W / SPECTRO_COLS;

    for (let col = 0; col < spectroHistory.length; col++) {
        const colData = spectroHistory[col];
        const binH = H / colData.length;
        for (let b = 0; b < colData.length; b++) {
            const val = colData[b] / 255;
            const hue = 240 - val * 240;
            ctx.fillStyle = `hsl(${hue}, 100%, ${val * 60 + 10}%)`;
            ctx.fillRect(col * colW, H - (b + 1) * binH, colW + 1, binH + 1);
        }
    }

    spectroFrameId = requestAnimationFrame(drawSpectrogram);
}

// ── Start / Stop / Reset Monitoring ────────────────────────────────
async function startMonitoring() {
    if (isMonitoring) return;

    try {
        stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
        });
    } catch (err) {
        console.error("Microphone access denied:", err);
        return;
    }

    audioCtx = new AudioContext();
    nativeSR = audioCtx.sampleRate;

    analyserNode = audioCtx.createAnalyser();
    analyserNode.fftSize = 2048;
    analyserNode.smoothingTimeConstant = 0.7;

    sourceNode = audioCtx.createMediaStreamSource(stream);
    sourceNode.connect(analyserNode);

    await audioCtx.audioWorklet.addModule("/static/js/audio-processor.js");
    workletNode = new AudioWorkletNode(audioCtx, "audio-chunk-processor");
    sourceNode.connect(workletNode);

    pcmBuffer = [];
    workletNode.port.onmessage = (e) => {
        const raw = e.data;
        const down = downsample(raw, nativeSR, TARGET_SR);
        pcmBuffer.push(...down);

        // Safety: Prevent buffer overflow (e.g. if tab was backgrounded)
        // If > 10 chunks (5 seconds) accumulated, clear to avoid packet burst
        if (pcmBuffer.length > CHUNK_SAMPLES * 10) {
            console.warn("Buffer overflow (tab backgrounded?), clearing buffer to prevent server crash.");
            pcmBuffer = [];
            return;
        }

        // Send 500ms chunks with 50% overlap
        const slideBy = Math.floor(CHUNK_SAMPLES * (1 - OVERLAP));

        // Limit to sending at most 2 chunks per tick to prevent "Too many packets"
        let chunksSent = 0;
        while (pcmBuffer.length >= CHUNK_SAMPLES && chunksSent < 2) {
            const chunk = new Float32Array(pcmBuffer.slice(0, CHUNK_SAMPLES));
            socket.emit("audio_chunk", chunk.buffer);
            pcmBuffer.splice(0, slideBy);
            chunksSent++;
        }

        // If we still have data, it will be processed in next message event (or we drop it?)
        // Better to drop if we are falling behind significantly
        if (pcmBuffer.length > CHUNK_SAMPLES * 4) {
            pcmBuffer.splice(0, pcmBuffer.length - CHUNK_SAMPLES);
        }
    };

    isMonitoring = true;
    btnStart.disabled = true;
    btnStop.disabled = false;
    statusDot.classList.add("live");
    statusText.textContent = "LIVE";

    drawWaveform();
    drawSpectrogram();
}

function stopMonitoring() {
    if (!isMonitoring) return;
    isMonitoring = false;

    if (workletNode) { workletNode.disconnect(); workletNode = null; }
    if (sourceNode) { sourceNode.disconnect(); sourceNode = null; }
    if (analyserNode) { analyserNode.disconnect(); analyserNode = null; }
    if (audioCtx) { audioCtx.close(); audioCtx = null; }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null; }
    if (spectroFrameId) { cancelAnimationFrame(spectroFrameId); spectroFrameId = null; }

    pcmBuffer = [];
    spectroHistory = [];

    btnStart.disabled = false;
    btnStop.disabled = true;
    statusDot.classList.remove("live");
    statusText.textContent = "OFFLINE";

    waveCanvas.getContext("2d").clearRect(0, 0, waveCanvas.width, waveCanvas.height);
    spectroCanvas.getContext("2d").clearRect(0, 0, spectroCanvas.width, spectroCanvas.height);
}

function resetAll() {
    // Stop monitoring if running
    stopMonitoring();

    // Clear all UI state
    clearLogs();
    coughCount = 0;
    sneezeCount = 0;
    updateStats();

    // Reset classification display
    predLabel.textContent = "Waiting…";
    predLabel.className = "pred-label";
    predConf.textContent = "—";
    predIcon.textContent = "🎙️";
    predIcon.className = "pred-icon";

    // Reset all bars
    updateBar(coughBar, coughVal, 0);
    updateBar(sneezeBar, sneezeVal, 0);
    updateBar(talkingBar, talkingVal, 0);
    updateBar(noiseBar, noiseVal, 0);

    // Tell the server to clear its buffer
    socket.emit("reset");

    // Show empty state
    showEmptyState();
}

// ── Socket Events ──────────────────────────────────────────────────
socket.on("classification", (data) => {
    updateBar(coughBar, coughVal, data.Cough);
    updateBar(sneezeBar, sneezeVal, data.Sneeze);
    updateBar(talkingBar, talkingVal, data.Talking);
    updateBar(noiseBar, noiseVal, data.Noise);

    predLabel.textContent = data.predicted;
    predConf.textContent = data.confidence + "%";
    predLabel.className = "pred-label " + data.predicted.toLowerCase();
    predIcon.className = "pred-icon " + data.predicted.toLowerCase();
    predIcon.textContent = classIcon(data.predicted);
});

socket.on("alert", (data) => {
    hideEmptyState();

    totalAlerts++;
    if (data.type === "Cough") coughCount++;
    if (data.type === "Sneeze") sneezeCount++;
    updateStats();
    alertCount.textContent = totalAlerts;

    const entry = document.createElement("div");
    entry.className = "alert-entry " + data.type.toLowerCase();
    entry.innerHTML = `
        <span class="alert-time">[${data.timestamp}]</span>
        <span class="alert-tag tag-${data.type.toLowerCase()}">${data.type}</span>
        <span class="alert-conf">${data.confidence}% confidence</span>
    `;

    alertList.prepend(entry);
    requestAnimationFrame(() => entry.classList.add("visible"));
});

socket.on("reset_ack", () => {
    console.log("Server state reset acknowledged");
});

// ── Utilities ──────────────────────────────────────────────────────
function updateBar(barEl, valEl, pct) {
    barEl.style.width = pct + "%";
    valEl.textContent = pct + "%";
    if (pct > 70) barEl.classList.add("high");
    else barEl.classList.remove("high");
}

function updateStats() {
    if (statCough) statCough.textContent = coughCount;
    if (statSneeze) statSneeze.textContent = sneezeCount;
    if (statTotal) statTotal.textContent = totalAlerts;
}

function clearLogs() {
    // Remove only alert entries, keep empty state
    const entries = alertList.querySelectorAll(".alert-entry");
    entries.forEach(e => e.remove());
    totalAlerts = 0;
    coughCount = 0;
    sneezeCount = 0;
    alertCount.textContent = "0";
    updateStats();
    showEmptyState();
}

function hideEmptyState() {
    if (emptyAlerts) emptyAlerts.style.display = "none";
}

function showEmptyState() {
    if (emptyAlerts) emptyAlerts.style.display = "flex";
}

// ── Event Listeners ────────────────────────────────────────────────
btnStart.addEventListener("click", startMonitoring);
btnStop.addEventListener("click", stopMonitoring);
btnReset.addEventListener("click", resetAll);
btnClearLogs.addEventListener("click", clearLogs);

// Resize canvases to parent
function resizeCanvases() {
    const waveWrap = waveCanvas.parentElement;
    const spectroWrap = spectroCanvas.parentElement;
    waveCanvas.width = waveWrap.clientWidth;
    waveCanvas.height = waveWrap.clientHeight;
    spectroCanvas.width = spectroWrap.clientWidth;
    spectroCanvas.height = spectroWrap.clientHeight;
}
window.addEventListener("resize", resizeCanvases);
window.addEventListener("load", resizeCanvases);
