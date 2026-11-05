/**
 * fall_detection_tfjs.js — in-browser live fall monitoring (TensorFlow.js MoveNet)
 *
 * Pose estimation : MoveNet (Lightning by default, Thunder optional) — runs on the device,
 *                   no video leaves the browser.
 * Decision layer  : FallInferenceEngine (static/js/fall-inference-engine.js), the exact
 *                   twin of the backend Python engine — kinematics + posture + time
 *                   state machine with plain-language evidence for every alert.
 *
 * The previous FallDetectorTFJS heuristic is gone: its angle test was inverted
 * (upright torso counted as a fall cue; lying counted as "standing"), speeds were
 * raw px/s (depends on distance to camera) and it had no notion of staying on the
 * floor, getting up, or lying still.
 *
 * TFJSLiveSession(videoEl, canvasEl, {
 *     sensitivity: 'low'|'medium'|'high',
 *     modelType:   'lightning'|'thunder',
 *     bedZones:    [[[x,y]...]...]        // normalised 0..1, lying here = resting
 *     onFall(event)                       // fall_confirmed (with evidence + explanation)
 *     onEvent(event)                      // recovered / long_lie / candidate_rejected
 *     onFrame(features, fps, result)
 * })
 */
'use strict';

const SKELETON_CONNECTIONS = [
    [0, 1], [0, 2], [1, 3], [2, 4], [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
    [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
];

const STATE_UI = {
    no_person:       { text: 'Scanning… (step back so the full body is visible)', color: '#9e9e9e' },
    normal:          { text: '● Monitoring', color: '#39ff14' },
    descent:         { text: '▼ Rapid drop detected…', color: '#ffb300' },
    on_ground_check: { text: '⚠ On the ground — verifying', color: '#ff8c00' },
    fall_confirmed:  { text: '⚠ FALL DETECTED', color: '#ff3b3b' },
    long_lie:        { text: '⚠ FALL — NOT MOVING', color: '#ff1744' },
    lying_in_bed:    { text: '☾ Resting in bed', color: '#64b5f6' },
};

function drawPose(ctx, keypoints, color, minScore = 0.3) {
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    for (const [a, b] of SKELETON_CONNECTIONS) {
        const A = keypoints[a], B = keypoints[b];
        if (!A || !B || A.score < minScore || B.score < minScore) continue;
        ctx.beginPath(); ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y); ctx.stroke();
    }
    for (const kp of keypoints) {
        if (!kp || kp.score < minScore) continue;
        ctx.beginPath(); ctx.arc(kp.x, kp.y, 4, 0, 2 * Math.PI);
        ctx.fillStyle = color; ctx.fill();
    }
}

function drawZones(ctx, W, H, zones, draft) {
    ctx.save();
    ctx.lineWidth = 2;
    for (const z of zones) {
        ctx.beginPath();
        z.forEach(([x, y], i) => (i ? ctx.lineTo(x * W, y * H) : ctx.moveTo(x * W, y * H)));
        ctx.closePath();
        ctx.fillStyle = 'rgba(100,181,246,0.15)'; ctx.fill();
        ctx.strokeStyle = 'rgba(100,181,246,0.9)'; ctx.stroke();
        ctx.fillStyle = '#90caf9'; ctx.font = 'bold 13px "Segoe UI", sans-serif';
        ctx.fillText('BED / SOFA', z[0][0] * W + 6, z[0][1] * H + 18);
    }
    if (draft && draft.length) {
        ctx.setLineDash([6, 4]); ctx.strokeStyle = '#ffeb3b';
        ctx.beginPath();
        draft.forEach(([x, y], i) => (i ? ctx.lineTo(x * W, y * H) : ctx.moveTo(x * W, y * H)));
        ctx.stroke(); ctx.setLineDash([]);
        for (const [x, y] of draft) { ctx.beginPath(); ctx.arc(x * W, y * H, 5, 0, 2 * Math.PI); ctx.fillStyle = '#ffeb3b'; ctx.fill(); }
    }
    ctx.restore();
}

function wrapText(ctx, text, maxW) {
    const words = text.split(' '); const lines = []; let cur = '';
    for (const w of words) {
        const test = cur ? cur + ' ' + w : w;
        if (ctx.measureText(test).width > maxW && cur) { lines.push(cur); cur = w; } else cur = test;
    }
    if (cur) lines.push(cur);
    return lines;
}

function drawOverlay(ctx, W, H, result, fps) {
    const ui = STATE_UI[result.state] || STATE_UI.normal;
    const fallen = result.fall_active;

    // top banner
    if (fallen) {
        const alpha = 0.55 + 0.2 * Math.sin(Date.now() / 200);
        ctx.fillStyle = `rgba(200, 20, 20, ${alpha})`;
        ctx.fillRect(0, 0, W, 54);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 24px "Segoe UI", sans-serif';
        ctx.fillText(ui.text, 14, 34);
        if (result.time_on_ground_s) {
            ctx.font = '15px "Segoe UI", sans-serif';
            ctx.fillText(`${Math.round(result.time_on_ground_s)} s on the floor`, W - 170, 34);
        }
    } else {
        ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, 0, W, 34);
        ctx.fillStyle = ui.color; ctx.font = 'bold 15px "Segoe UI", sans-serif';
        ctx.fillText(ui.text, 12, 22);
        ctx.fillStyle = '#bbb'; ctx.font = '12px "Segoe UI", sans-serif';
        ctx.fillText(`FPS ${fps.toFixed(0)}`, W - 62, 22);
    }

    // bottom panel: the inference itself
    const lines = [];
    const ev = result.fall_event;
    if (fallen && ev) {
        lines.push({ t: `${(ev.fall_type || 'fall').replace(/_/g, ' ').toUpperCase()} · confidence ${(ev.confidence * 100).toFixed(0)}% · ${ev.severity}`, c: '#ffcc80', b: true });
        for (const e of (ev.evidence || []).slice(0, 5)) lines.push({ t: `${e.passed ? '✔' : '•'} ${e.text}`, c: e.passed ? '#fff' : '#aaa' });
    } else if (result.live && result.live.head_height != null) {
        const L = result.live;
        lines.push({ t: `Head ${Math.round(L.head_height * 100)}% · Hips ${Math.round(L.hip_height * 100)}% of standing height · Torso ${Math.round(L.torso_angle)}°`, c: '#e0e0e0' });
        const flags = [L.on_ground ? 'ON GROUND' : L.upright ? 'upright' : 'low / seated',
            L.in_bed_zone ? 'in bed zone' : null, L.calibrated ? null : 'calibrating — stand in view once',
            L.motion != null ? `motion ${L.motion.toFixed(2)}` : null].filter(Boolean);
        lines.push({ t: flags.join(' · '), c: L.on_ground ? '#ffb74d' : '#9e9e9e' });
    }
    if (lines.length) {
        ctx.font = '13px "Segoe UI", sans-serif';
        const wrapped = [];
        for (const l of lines) for (const s of wrapText(ctx, l.t, W - 24)) wrapped.push({ ...l, t: s });
        const ph = 12 + wrapped.length * 19;
        ctx.fillStyle = 'rgba(0,0,0,0.62)'; ctx.fillRect(0, H - ph, W, ph);
        wrapped.forEach((l, i) => {
            ctx.font = (l.b ? 'bold ' : '') + '13px "Segoe UI", sans-serif';
            ctx.fillStyle = l.c; ctx.fillText(l.t, 12, H - ph + 20 + i * 19);
        });
    }
}

class TFJSLiveSession {
    constructor(videoEl, canvasEl, opts = {}) {
        this.videoEl = videoEl;
        this.canvasEl = canvasEl;
        this.ctx = canvasEl.getContext('2d');
        this.onFall = opts.onFall || (() => {});
        this.onEvent = opts.onEvent || (() => {});
        this.onFrame = opts.onFrame || (() => {});
        this.modelType = opts.modelType || 'lightning';
        this.bedZones = opts.bedZones || TFJSLiveSession.loadZones();
        this.engine = new FallInferenceEngine({ sensitivity: opts.sensitivity || 'medium', bedZones: this.bedZones });
        this._poseDetector = null; this._running = false; this._rafId = null; this._stream = null;
        this._frameTimes = []; this._fps = 0;
        this._draft = null;
        this._onCanvasClick = this._onCanvasClick.bind(this);
    }

    static loadZones() {
        try { return JSON.parse(localStorage.getItem('caretaker.bedZones') || '[]'); } catch (e) { return []; }
    }
    static saveZones(z) {
        try { localStorage.setItem('caretaker.bedZones', JSON.stringify(z)); } catch (e) { /* storage unavailable */ }
    }

    /** Click 4 corners of the bed/sofa on the video to mark it as a resting zone. */
    startZoneDrawing() { this._draft = []; this.canvasEl.style.cursor = 'crosshair'; this.canvasEl.addEventListener('click', this._onCanvasClick); }
    clearZones() { this.bedZones = []; this.engine.setBedZones([]); TFJSLiveSession.saveZones([]); }
    _onCanvasClick(e) {
        const r = this.canvasEl.getBoundingClientRect();
        this._draft.push([(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]);
        if (this._draft.length === 4) {
            this.bedZones = this.bedZones.concat([this._draft]);
            this.engine.setBedZones(this.bedZones);
            TFJSLiveSession.saveZones(this.bedZones);
            this._draft = null;
            this.canvasEl.style.cursor = '';
            this.canvasEl.removeEventListener('click', this._onCanvasClick);
        }
    }

    async start(deviceId = null) {
        if (this._running) return;
        const model = poseDetection.SupportedModels.MoveNet;
        this._poseDetector = await poseDetection.createDetector(model, {
            modelType: this.modelType === 'thunder'
                ? poseDetection.movenet.modelType.SINGLEPOSE_THUNDER
                : poseDetection.movenet.modelType.SINGLEPOSE_LIGHTNING,
            enableSmoothing: true,
        });
        const constraints = {
            video: deviceId ? { deviceId: { exact: deviceId }, width: 640, height: 480 } : { width: 640, height: 480, facingMode: 'user' },
            audio: false,
        };
        this._stream = await navigator.mediaDevices.getUserMedia(constraints);
        this.videoEl.srcObject = this._stream;
        await new Promise(res => { this.videoEl.onloadedmetadata = res; });
        await this.videoEl.play();
        this.canvasEl.width = this.videoEl.videoWidth || 640;
        this.canvasEl.height = this.videoEl.videoHeight || 480;
        this.engine.reset();
        this._running = true;
        this._loop();
    }

    async _loop() {
        if (!this._running) return;
        const W = this.canvasEl.width, H = this.canvasEl.height;
        let poses = [];
        try { poses = await this._poseDetector.estimatePoses(this.videoEl); } catch (err) { console.error('[TFJSLiveSession] pose error:', err); }

        this.ctx.save(); this.ctx.scale(-1, 1); this.ctx.translate(-W, 0);
        this.ctx.drawImage(this.videoEl, 0, 0, W, H); this.ctx.restore();

        const t = performance.now() / 1000;
        let kps = null;
        if (poses && poses.length && (poses[0].score == null || poses[0].score > 0.2)) {
            kps = poses[0].keypoints.map(kp => ({ ...kp, x: W - kp.x }));   // mirror to match the drawn frame
        }
        const result = kps
            ? this.engine.update(t, kps.map(k => [k.x, k.y]), kps.map(k => k.score), [W, H])
            : this.engine.update(t, null);

        drawZones(this.ctx, W, H, this.bedZones, this._draft);
        if (kps) drawPose(this.ctx, kps, result.fall_active ? '#ff3b3b' : result.state === 'on_ground_check' ? '#ff8c00' : '#00e5ff');

        for (const ev of result.events) {
            const payload = { ...ev, timestamp: new Date().toISOString() };
            if (ev.type === 'fall_confirmed') this.onFall(payload);
            else this.onEvent(payload);
        }

        const now = performance.now();
        this._frameTimes.push(now);
        if (this._frameTimes.length > 30) this._frameTimes.shift();
        if (this._frameTimes.length >= 2) {
            this._fps = ((this._frameTimes.length - 1) / (this._frameTimes[this._frameTimes.length - 1] - this._frameTimes[0])) * 1000;
        }
        drawOverlay(this.ctx, W, H, result, this._fps);
        const L = result.live || {};
        this.onFrame({ torsoAngle: L.torso_angle, headHeight: L.head_height, hipHeight: L.hip_height,
            state: result.state, onGround: L.on_ground }, this._fps, result);

        this._rafId = requestAnimationFrame(() => this._loop());
    }

    stop() {
        this._running = false;
        if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
        if (this._stream) { this._stream.getTracks().forEach(t => t.stop()); this._stream = null; }
        this.videoEl.srcObject = null;
        this.engine.reset();
        this.canvasEl.removeEventListener('click', this._onCanvasClick);
        this.ctx.clearRect(0, 0, this.canvasEl.width, this.canvasEl.height);
    }

    get isRunning() { return this._running; }
    get fps() { return this._fps; }
}
