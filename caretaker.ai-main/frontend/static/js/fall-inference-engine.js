/**
 * fall-inference-engine.js — browser twin of backend/VideoMonitoring/fall_inference.py
 *
 * SAME logic, thresholds and outputs as the Python engine (a parity test runs
 * both on identical synthetic sequences: frontend/tests/fall_engine_parity.test.js).
 *
 * Replaces the old FallDetectorTFJS heuristic, which had an inverted angle
 * check (it counted an UPRIGHT torso as a fall cue and treated LYING as
 * "standing"), used raw px/s speeds (camera-distance dependent) and had no
 * notion of "stayed on the floor", "got up" or "lying still".
 *
 * Usage:
 *   const eng = new FallInferenceEngine({ sensitivity: 'medium', bedZones: [] });
 *   const r = eng.update(tSeconds, keypointsXY /* [[x,y]×17] or null *\/, confidences, [w, h]);
 *   r.state, r.events (fall_confirmed / recovered / long_lie / candidate_rejected), r.live
 */
(function (root) {
    'use strict';

    const NOSE = 0, L_EYE = 1, R_EYE = 2, L_EAR = 3, R_EAR = 4;
    const L_SHO = 5, R_SHO = 6, L_HIP = 11, R_HIP = 12, L_ANK = 15, R_ANK = 16;
    const HEAD_IDX = [NOSE, L_EYE, R_EYE, L_EAR, R_EAR];

    const NO_PERSON = 'no_person', NORMAL = 'normal', DESCENT = 'descent', ON_GROUND_CHECK = 'on_ground_check',
        FALL_CONFIRMED = 'fall_confirmed', LONG_LIE = 'long_lie', LYING_IN_BED = 'lying_in_bed';
    const EV_FALL = 'fall_confirmed', EV_RECOVERED = 'recovered', EV_LONG_LIE = 'long_lie', EV_REJECTED = 'candidate_rejected';

    const PRESETS = {
        low:    { v_fast: 1.10, drop_fast: 0.35, confirm_s: 2.5, slow_floor_s: 15.0, long_lie_s: 45.0, min_score: 0.45 },
        medium: { v_fast: 0.85, drop_fast: 0.28, confirm_s: 1.5, slow_floor_s: 8.0,  long_lie_s: 25.0, min_score: 0.35 },
        high:   { v_fast: 0.65, drop_fast: 0.22, confirm_s: 1.0, slow_floor_s: 5.0,  long_lie_s: 15.0, min_score: 0.25 },
    };

    const HIP_ON_FLOOR = 0.15, HEAD_LOW = 0.35, HEAD_LOWISH = 0.45, HIP_LYING_MAX = 0.25, EXTENT_COLLAPSED = 0.45;
    const UPRIGHT_HEAD = 0.72, UPRIGHT_ANGLE = 35.0, LYING_ANGLE = 55.0;
    const KP_MIN_CONF = 0.3, DESCENT_WINDOW_S = 1.5, SLOW_WINDOW_S = 6.0, DESCENT_TIMEOUT_S = 2.5;
    const LOST_DURING_DESCENT_S = 1.0, LOST_RESET_S = 2.0, RECOVER_HOLD_S = 2.0, COOLDOWN_S = 5.0;
    const STILL_MOTION = 0.12, VEL_MIN_DT = 0.2;

    const clip01 = x => (x < 0 ? 0 : x > 1 ? 1 : x);
    const meanPt = pts => (pts.length ? [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length] : null);
    const r1 = x => Math.round(x * 10) / 10, r2 = x => Math.round(x * 100) / 100, r3 = x => Math.round(x * 1000) / 1000;
    const maxBy = (arr, f) => { let best = arr[0]; for (const a of arr) if (f(a) > f(best)) best = a; return best; };

    function pointInPolygon(x, y, poly) {
        let inside = false;
        const n = poly.length;
        if (n < 3) return false;
        for (let i = 0, j = n - 1; i < n; j = i++) {
            const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
            if ((yi > y) !== (yj > y)) {
                const xc = (xj - xi) * (y - yi) / ((yj - yi) || 1e-9) + xi;
                if (x < xc) inside = !inside;
            }
        }
        return inside;
    }

    class FallInferenceEngine {
        constructor(opts = {}) {
            const sens = PRESETS[opts.sensitivity] ? opts.sensitivity : 'medium';
            this.sensitivity = sens;
            this.cfg = Object.assign({}, PRESETS[sens]);
            if (opts.longLieS != null) this.cfg.long_lie_s = Number(opts.longLieS);
            this.bedZones = (opts.bedZones || []).map(z => z.map(p => [p[0], p[1]]));
            this.reset();
        }

        reset() {
            this.state = NO_PERSON;
            this.hRef = null; this.torsoRef = null; this.floorY = null;
            this.history = [];
            this.candidate = null;
            this.lastSeenT = null; this.lastT = null;
            this.cooldownUntil = -1e9;
            this.uprightSince = null; this.stillSince = null;
            this.fallT = null; this.fallEvent = null; this.longLieFired = false;
            this.eventCounter = 0;
            this._smooth = new Array(17).fill(null);
            this._pairOff = {};
            this.floorSince = null; this._lastFloorT = null; this._lostChecked = false;
        }

        setBedZones(zones) { this.bedZones = (zones || []).map(z => z.map(p => [p[0], p[1]])); }

        update(t, kpsXY, kpsConf = null, frameSize = null, lstmProb = null) {
            const events = [];
            const dt = this.lastT == null ? 0 : Math.max(0, t - this.lastT);
            this.lastT = t;

            const obs = this._observe(t, dt, kpsXY, kpsConf);
            if (!obs) { this._onLost(t, events); return this._result(t, null, events, lstmProb); }

            this.lastSeenT = t;
            this._lostChecked = false;
            const s = obs.sample;
            if (s.onFloor) {
                if (this.floorSince == null) this.floorSince = t;
                this._lastFloorT = t;
            } else if (this.floorSince != null && this._lastFloorT != null && t - this._lastFloorT > 1.0) {
                this.floorSince = null;
            }
            this.history.push(s);
            while (this.history.length && t - this.history[0].t > SLOW_WINDOW_S + 0.5) this.history.shift();

            const inBed = this._inBed(s.hipXY, frameSize);
            obs.inBed = inBed;
            if (this.state === NO_PERSON) this.state = NORMAL;

            if (s.upright) { if (this.uprightSince == null) this.uprightSince = t; } else this.uprightSince = null;
            const motion = this._motion(t);
            obs.motion = motion;
            if (motion != null && motion < STILL_MOTION) { if (this.stillSince == null) this.stillSince = t; } else this.stillSince = null;

            if (lstmProb != null && this.candidate) this.candidate.lstmMax = Math.max(this.candidate.lstmMax, Number(lstmProb));

            if (this.state === NORMAL) this._stepNormal(t, s, inBed, lstmProb, events);
            else if (this.state === DESCENT) this._stepDescent(t, s, events);
            else if (this.state === ON_GROUND_CHECK) this._stepGroundCheck(t, s, inBed, events);
            else if (this.state === FALL_CONFIRMED || this.state === LONG_LIE) this._stepFallen(t, s, events);
            else if (this.state === LYING_IN_BED) {
                if (s.upright || (!s.onGround && s.headH > HEAD_LOWISH)) this.state = NORMAL;
            }
            return this._result(t, obs, events, lstmProb);
        }

        // ── geometry ──────────────────────────────────────────────────────
        _observe(t, dt, kpsXY, kpsConf) {
            if (!kpsXY) return null;
            const pts = [];
            for (let i = 0; i < 17; i++) {
                const x = Number(kpsXY[i][0]), y = Number(kpsXY[i][1]);
                const c = kpsConf == null ? 1.0 : Number(kpsConf[i]);
                pts.push(c < KP_MIN_CONF || (x === 0 && y === 0) ? null : [x, y]);
            }
            const alpha = dt <= 0 ? 1.0 : 1.0 - Math.exp(-dt / 0.05);
            const sm = pts.map((p, i) => {
                const prev = this._smooth[i];
                if (!p) return null;
                if (!prev || dt > 0.5) return p;
                return [prev[0] + alpha * (p[0] - prev[0]), prev[1] + alpha * (p[1] - prev[1])];
            });
            this._smooth = sm;

            const sho = this._pairMid('sho', sm[L_SHO], sm[R_SHO]);
            const hip = this._pairMid('hip', sm[L_HIP], sm[R_HIP]);
            if (!sho || !hip) return null;
            const valid = sm.filter(p => p);
            if (valid.length < 5) return null;

            const head = meanPt(HEAD_IDX.map(i => sm[i]).filter(p => p)) || sho;
            const ank = this._pairMid('ank', sm[L_ANK], sm[R_ANK]);
            const ys = valid.map(p => p[1]), xs = valid.map(p => p[0]);
            const extH = Math.max(...ys) - Math.min(...ys);
            const extW = Math.max(...xs) - Math.min(...xs);
            const dx = sho[0] - hip[0], dy = sho[1] - hip[1];
            const torso = Math.hypot(dx, dy);
            const angle = Math.atan2(Math.abs(dx), -dy) * 180 / Math.PI;

            const standing = angle < 25 && ank && extH > 1.3 * Math.max(extW, 1e-6) && (ank[1] - hip[1]) > 0.45 * extH;
            if (standing) {
                if (this.hRef == null) { this.hRef = extH; this.torsoRef = torso; this.floorY = ank[1]; }
                else {
                    const ddt = Math.max(dt, 1e-3);
                    const tau = extH > this.hRef ? 0.5 : 5.0;
                    const a = 1.0 - Math.exp(-ddt / tau);
                    this.hRef += a * (extH - this.hRef);
                    this.torsoRef += a * (torso - this.torsoRef);
                    const af = 1.0 - Math.exp(-ddt / 0.4);
                    this.floorY += af * (ank[1] - this.floorY);
                }
            }
            let hRef = this.hRef;
            if (hRef == null) hRef = Math.max(torso * 3.2, extH, 1.0);
            const floorY = this.floorY != null ? this.floorY : Math.max(...ys);
            const headH = (floorY - head[1]) / hRef, hipH = (floorY - hip[1]) / hRef, extent = extH / hRef;

            let onFloor, onGround;
            if (this.hRef != null) {
                onFloor = hipH < HIP_ON_FLOOR || (headH < HEAD_LOW && angle > LYING_ANGLE && hipH < HIP_LYING_MAX);
                onGround = onFloor || (extent < EXTENT_COLLAPSED && headH < HEAD_LOWISH);
            } else {
                onFloor = onGround = angle > 60 && extW > 1.2 * extH;
            }
            const upright = angle < UPRIGHT_ANGLE && headH > UPRIGHT_HEAD && !onGround;
            return {
                sample: { t, headH, hipH, angle, extent, onGround, onFloor, upright, kps: sm, hipXY: hip },
                calibrated: this.hRef != null,
            };
        }

        _pairMid(key, a, b) {
            if (a && b) { this._pairOff[key] = [b[0] - a[0], b[1] - a[1]]; return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; }
            const off = this._pairOff[key];
            if (a && off) return [a[0] + off[0] / 2, a[1] + off[1] / 2];
            if (b && off) return [b[0] - off[0] / 2, b[1] - off[1] / 2];
            return a || b || null;
        }

        _inBed(hipXY, frameSize) {
            if (!this.bedZones.length || !frameSize) return false;
            const [w, h] = frameSize;
            if (!w || !h) return false;
            const nx = hipXY[0] / w, ny = hipXY[1] / h;
            return this.bedZones.some(z => pointInPolygon(nx, ny, z));
        }

        _motion(t) {
            if (!this.history.length || t - this.history[0].t < 1.4) return null;
            const recent = this.history.filter(s => t - s.t <= 0.5);
            const past = this.history.filter(s => t - s.t >= 1.0 && t - s.t <= 1.5);
            if (recent.length < 2 || past.length < 2) return null;
            const avg = (group, i) => {
                const pts = group.map(g => g.kps[i]).filter(p => p);
                return pts.length >= Math.max(1, Math.floor(group.length / 2)) ? meanPt(pts) : null;
            };
            const ref = this.torsoRef || 1.0;
            const d = [];
            for (let i = 0; i < 17; i++) {
                const a = avg(recent, i), b = avg(past, i);
                if (a && b) d.push(Math.hypot(a[0] - b[0], a[1] - b[1]));
            }
            if (d.length < 4) return null;
            return (d.reduce((x, y) => x + y, 0) / d.length) / ref;
        }

        _window(t, span) { return this.history.filter(s => t - s.t <= span); }

        _peakDownSpeed(samples, attr) {
            let best = 0.0;
            for (let i = 0; i < samples.length; i++) {
                let k = i - 1;
                while (k >= 0 && samples[i].t - samples[k].t < VEL_MIN_DT) k--;
                if (k < 0) continue;
                const gap = samples[i].t - samples[k].t;
                if (gap <= 0 || gap > 0.6) continue;
                best = Math.max(best, (samples[k][attr] - samples[i][attr]) / gap);
            }
            return best;
        }

        _newCandidate(o) {
            return Object.assign({ kind: 'fast', tStart: 0, tLow: null, peakV: 0, headDrop: 0, hipDrop: 0, angleBefore: 0,
                angleAfter: 0, descentS: 0, groundFrames: 0, floorFrames: 0, totalFrames: 0, lstmMax: 0, startHeadH: 1 }, o);
        }

        // ── states ────────────────────────────────────────────────────────
        _stepNormal(t, s, inBed, lstmProb, events) {
            if (t < this.cooldownUntil) return;
            const win = this._window(t, DESCENT_WINDOW_S);
            if (win.length >= 3) {
                const peak = maxBy(win, x => x.headH);
                const headDrop = peak.headH - s.headH;
                const after = win.filter(x => x.t >= peak.t);
                const v = Math.max(this._peakDownSpeed(after, 'headH'), this._peakDownSpeed(after, 'hipH'));
                if (v >= this.cfg.v_fast && headDrop >= this.cfg.drop_fast) {
                    const t0 = Math.max(...win.filter(x => x.headH >= peak.headH - 0.05).map(x => x.t));
                    this.candidate = this._newCandidate({
                        kind: 'fast', tStart: t0, peakV: v, headDrop, hipDrop: Math.max(0, peak.hipH - s.hipH),
                        angleBefore: Math.min(...win.filter(x => x.t <= peak.t + 1e-9).map(x => x.angle)),
                        startHeadH: peak.headH, lstmMax: Number(lstmProb || 0),
                    });
                    this.state = DESCENT;
                    this._stepDescent(t, s, events);
                    return;
                }
            }
            if (inBed && (s.onGround || s.angle > LYING_ANGLE)) { this.state = LYING_IN_BED; return; }
            if (s.onFloor && !inBed && this.floorSince != null && t - this.floorSince >= 0.5) {
                const slow = this._window(t, SLOW_WINDOW_S);
                const prior = slow.filter(x => !x.onGround && x.headH >= 0.55);
                if (prior.length) {
                    const top = maxBy(prior, x => x.headH);
                    this.candidate = this._newCandidate({
                        kind: 'slow', tStart: top.t, tLow: t,
                        peakV: this._peakDownSpeed(slow.filter(x => x.t >= top.t), 'headH'),
                        headDrop: top.headH - s.headH, hipDrop: Math.max(0, top.hipH - s.hipH),
                        angleBefore: top.angle, startHeadH: top.headH, lstmMax: Number(lstmProb || 0),
                    });
                    this.candidate.descentS = t - top.t;
                    this.state = ON_GROUND_CHECK;
                    this._stepGroundCheck(t, s, inBed, events);
                    return;
                }
                if (this.floorSince != null && t - this.floorSince >= this.cfg.slow_floor_s) {
                    this.candidate = this._newCandidate({ kind: 'found', tStart: this.floorSince, tLow: this.floorSince,
                        angleBefore: s.angle, startHeadH: s.headH, lstmMax: Number(lstmProb || 0) });
                    this._confirm(t, s, events, 'found_on_floor');
                }
            }
        }

        _stepDescent(t, s, events) {
            const c = this.candidate;
            if (!c) { this.state = NORMAL; return; }
            const win = this.history.filter(x => x.t >= c.tStart);
            c.peakV = Math.max(c.peakV, this._peakDownSpeed(win, 'headH'), this._peakDownSpeed(win, 'hipH'));
            c.headDrop = Math.max(c.headDrop, c.startHeadH - s.headH);
            if (s.onGround) {
                c.tLow = t; c.descentS = Math.max(0.05, t - c.tStart);
                this.state = ON_GROUND_CHECK;
                return;
            }
            if (t - c.tStart > DESCENT_TIMEOUT_S) {
                events.push(this._event(EV_REJECTED, t, s, { reason: 'sat down / bent over (did not end on the floor)' }));
                this.candidate = null; this.state = NORMAL;
            }
        }

        _stepGroundCheck(t, s, inBed, events) {
            const c = this.candidate;
            if (!c) { this.state = NORMAL; return; }
            c.totalFrames += 1;
            if (s.onGround) c.groundFrames += 1;
            if (s.onFloor) c.floorFrames += 1;
            c.angleAfter = Math.max(c.angleAfter, s.angle);
            c.headDrop = Math.max(c.headDrop, c.startHeadH - s.headH);

            if (inBed && c.peakV < 1.6) {
                events.push(this._event(EV_REJECTED, t, s, { reason: 'lying down in a bed / sofa zone' }));
                this.candidate = null; this.state = LYING_IN_BED; return;
            }
            if (s.upright && this.uprightSince != null && t - this.uprightSince >= 0.5) {
                events.push(this._event(EV_REJECTED, t, s, { reason: 'got straight back up (squat / bend / kneel)' }));
                this.candidate = null; this.state = NORMAL; return;
            }
            const tLow = c.tLow != null ? c.tLow : t;
            const need = this.cfg.confirm_s * (c.kind === 'slow' ? 2.0 : 1.0);
            if (t - tLow >= need) {
                const frac = c.groundFrames / Math.max(1, c.totalFrames);
                const floorOk = c.kind === 'slow'
                    ? c.floorFrames / Math.max(1, c.totalFrames) >= 0.6
                    : (c.floorFrames > 0 || c.peakV >= 1.3 * this.cfg.v_fast);
                if (frac >= 0.6 && floorOk) this._confirm(t, s, events, null);
                else {
                    events.push(this._event(EV_REJECTED, t, s, { reason: frac < 0.6 ? 'not consistently on the ground' : 'lying down above floor level (bed / sofa?)' }));
                    this.candidate = null; this.state = NORMAL;
                }
            }
        }

        _stepFallen(t, s, events) {
            const fallT = this.fallT != null ? this.fallT : t;
            if (s.upright && this.uprightSince != null && t - this.uprightSince >= RECOVER_HOLD_S) {
                const onGround = Math.max(0, (t - RECOVER_HOLD_S) - fallT);
                events.push(this._event(EV_RECOVERED, t, s, {
                    time_on_ground_s: r1(onGround),
                    related_event_id: (this.fallEvent || {}).event_id,
                    explanation: `Person got back up after about ${Math.round(onGround)} s on the ground.`,
                }));
                this.state = NORMAL; this.candidate = null; this.fallEvent = null;
                this.cooldownUntil = t + COOLDOWN_S;
                return;
            }
            if (this.state === FALL_CONFIRMED && !this.longLieFired && this.stillSince != null && t - this.stillSince >= this.cfg.long_lie_s) {
                this.longLieFired = true;
                this.state = LONG_LIE;
                const stillFor = t - this.stillSince;
                events.push(this._event(EV_LONG_LIE, t, s, {
                    severity: 'critical', still_for_s: r1(stillFor), time_on_ground_s: r1(t - fallT),
                    related_event_id: (this.fallEvent || {}).event_id,
                    explanation: `Still on the floor and barely moving for ${Math.round(stillFor)} s after the fall.`,
                }));
            } else if (this.state === LONG_LIE && this.stillSince == null) {
                this.state = FALL_CONFIRMED; this.longLieFired = false;
            }
        }

        _onLost(t, events) {
            if (this.lastSeenT == null) { this.state = NO_PERSON; return; }
            const gone = t - this.lastSeenT;
            if (this.state === DESCENT && gone >= LOST_DURING_DESCENT_S && this.candidate) {
                const s = this.history.length ? this.history[this.history.length - 1] : null;
                if (s && this.candidate.peakV >= this.cfg.v_fast) {
                    this.candidate.tLow = this.lastSeenT;
                    this._confirm(t, s, events, 'out_of_view');
                } else { this.candidate = null; this.state = NO_PERSON; }
                return;
            }
            if (this.state === NORMAL && gone >= LOST_DURING_DESCENT_S && !this._lostChecked && this.history.length && t >= this.cooldownUntil) {
                this._lostChecked = true;
                const last = this.history[this.history.length - 1];
                const win = this.history.filter(x => last.t - x.t <= 1.0);
                if (win.length >= 3) {
                    const top = maxBy(win, x => x.headH);
                    const after = win.filter(x => x.t >= top.t);
                    const v = Math.max(this._peakDownSpeed(after, 'headH'), this._peakDownSpeed(after, 'hipH'));
                    const drop = top.headH - last.headH;
                    if (v >= this.cfg.v_fast && drop >= 0.12 && top.upright) {
                        const t0 = Math.max(...win.filter(x => x.headH >= top.headH - 0.05).map(x => x.t));
                        this.candidate = this._newCandidate({ kind: 'fast', tStart: t0, tLow: this.lastSeenT, peakV: v,
                            headDrop: drop, angleBefore: top.angle, angleAfter: last.angle, startHeadH: top.headH,
                            descentS: last.t - t0 });
                        this._confirm(t, last, events, 'out_of_view');
                        return;
                    }
                }
            }
            if (this.state === FALL_CONFIRMED || this.state === LONG_LIE) return;
            const c = this.candidate;
            if (this.state === ON_GROUND_CHECK && c && c.groundFrames > 0 && c.tLow != null
                && t - c.tLow >= this.cfg.confirm_s && gone >= LOST_DURING_DESCENT_S) {
                const s = this.history.length ? this.history[this.history.length - 1] : null;
                if (s) { this._confirm(t, s, events, c.kind === 'fast' ? 'out_of_view' : 'slow_collapse'); return; }
            }
            if (gone >= LOST_RESET_S && [NORMAL, ON_GROUND_CHECK, LYING_IN_BED].includes(this.state)) {
                this.state = NO_PERSON; this.candidate = null; this.history = [];
            }
        }

        // ── confirmation ──────────────────────────────────────────────────
        _score(c, s, groundFrac) {
            const rot = Math.max(0, Math.max(c.angleAfter, s.angle) - c.angleBefore);
            const comps = [
                ['speed', 0.25, clip01((c.peakV - 0.4) / 1.0)],
                ['drop', 0.25, clip01((c.headDrop - 0.2) / 0.5)],
                ['rotation', 0.15, clip01((rot - 15.0) / 60.0)],
                ['ground', 0.25, clip01(groundFrac)],
            ];
            if (c.lstmMax > 0) comps.push(['learned_model', 0.10, clip01(c.lstmMax)]);
            const tot = comps.reduce((a, x) => a + x[1], 0);
            const score = comps.reduce((a, x) => a + x[1] * x[2], 0) / tot;
            return [score, comps.map(([n, w, v]) => ({ signal: n, weight: r2(w / tot), score: r2(v) }))];
        }

        _confirm(t, s, events, fallType) {
            const c = this.candidate;
            let groundFrac = c && c.totalFrames ? c.groundFrames / c.totalFrames : (s.onGround ? 1.0 : 0.0);
            if (fallType === 'out_of_view') groundFrac = 0.5;
            const [score, comps] = this._score(c, s, groundFrac);
            if (fallType == null) {
                fallType = c.kind === 'fast' ? ((c.peakV >= 1.2 && c.descentS <= 1.2) ? 'hard_fall' : 'fall') : 'slow_collapse';
            }
            const severity = fallType === 'out_of_view' ? 'high'
                : ((fallType === 'hard_fall' || fallType === 'fall') && score >= this.cfg.min_score ? 'high' : 'medium');
            const rot = Math.max(0, Math.max(c.angleAfter, s.angle) - c.angleBefore);

            const evidence = [];
            if (c.kind !== 'found') {
                evidence.push({ signal: 'head_drop', value: r2(c.headDrop), unit: 'of standing height', threshold: this.cfg.drop_fast,
                    passed: c.headDrop >= this.cfg.drop_fast,
                    text: `Head dropped ${Math.round(c.headDrop * 100)}% of standing height` + (c.descentS ? ` in ${c.descentS.toFixed(1)} s` : '') });
                evidence.push({ signal: 'peak_speed', value: r2(c.peakV), unit: 'standing-heights/s', threshold: this.cfg.v_fast,
                    passed: c.peakV >= this.cfg.v_fast,
                    text: `Peak downward speed ${c.peakV.toFixed(2)} body-heights/s` + (c.peakV >= this.cfg.v_fast ? ' (fast, uncontrolled)' : ' (slow)') });
                evidence.push({ signal: 'torso_rotation', value: r1(rot), unit: 'degrees', threshold: 30, passed: rot >= 30,
                    text: `Torso rotated ${Math.round(rot)}° (now ${Math.round(s.angle)}° from vertical)` });
            }
            if (fallType === 'out_of_view') {
                evidence.push({ signal: 'lost_from_view', value: r1(t - (c.tLow != null ? c.tLow : t)), unit: 's',
                    threshold: LOST_DURING_DESCENT_S, passed: true,
                    text: c.groundFrames > 0 ? "Reached the floor, then left the camera's view without getting up"
                        : 'Person disappeared from view mid-fall and has not reappeared' });
            }
            evidence.push({ signal: 'on_ground', value: r2(s.hipH), unit: 'hip height / standing height', threshold: HIP_ON_FLOOR,
                passed: s.onGround,
                text: s.onFloor ? `Body is at floor level (hips at ${Math.round(Math.max(0, s.hipH) * 100)}% of standing height)`
                    : `Body is low and collapsed (head at ${Math.round(Math.max(0, s.headH) * 100)}% of standing height)` });
            const held = t - (c.tLow != null ? c.tLow : t);
            evidence.push({ signal: 'stayed_down', value: r1(held), unit: 's', threshold: this.cfg.confirm_s,
                passed: held >= this.cfg.confirm_s || c.kind === 'found',
                text: `Stayed on the ground for ${held.toFixed(1)} s (did not get straight back up)` });
            if (c.lstmMax > 0) {
                evidence.push({ signal: 'learned_model', value: r2(c.lstmMax), unit: 'probability', threshold: 0.5,
                    passed: c.lstmMax >= 0.5, text: `Pose-sequence model fall probability ${c.lstmMax.toFixed(2)}` });
            }
            const phrases = { hard_fall: 'Hard fall', fall: 'Fall', slow_collapse: 'Slow collapse / slid to the floor',
                out_of_view: "Fall that continued out of the camera's view", found_on_floor: 'Person found lying on the floor' };
            const main = evidence.filter(e => e.passed).slice(0, 4).map(e => e.text);
            const ev = this._event(EV_FALL, t, s, {
                fall_type: fallType, severity, confidence: r2(score), score_breakdown: comps, evidence,
                explanation: `${phrases[fallType] || 'Fall'}: ${main.join('; ')}.`, descent_s: r2(c.descentS),
            });
            events.push(ev);
            this.fallEvent = ev;
            this.fallT = c.tLow != null ? c.tLow : t;
            this.longLieFired = false;
            this.state = FALL_CONFIRMED;
            this.candidate = null;
        }

        _event(type, t, s, extra) {
            this.eventCounter += 1;
            return Object.assign({ event_id: this.eventCounter, type, t: r3(t), state: this.state,
                position: [r1(s.hipXY[0]), r1(s.hipXY[1])] }, extra || {});
        }

        _result(t, obs, events, lstmProb) {
            const fallen = this.state === FALL_CONFIRMED || this.state === LONG_LIE;
            let live = {};
            if (obs) {
                const s = obs.sample;
                live = { head_height: r2(s.headH), hip_height: r2(s.hipH), torso_angle: r1(s.angle), extent: r2(s.extent),
                    on_ground: s.onGround, upright: s.upright, motion: obs.motion == null ? null : r3(obs.motion),
                    in_bed_zone: !!obs.inBed, calibrated: !!obs.calibrated };
                if (lstmProb != null) live.lstm_prob = r3(lstmProb);
            }
            return { state: this.state, fall_active: fallen, events, fall_event: fallen ? this.fallEvent : null,
                time_on_ground_s: fallen && this.fallT != null ? r1(t - this.fallT) : 0, live };
        }
    }

    FallInferenceEngine.STATES = { NO_PERSON, NORMAL, DESCENT, ON_GROUND_CHECK, FALL_CONFIRMED, LONG_LIE, LYING_IN_BED };
    FallInferenceEngine.PRESETS = PRESETS;

    if (typeof module !== 'undefined' && module.exports) module.exports = { FallInferenceEngine, pointInPolygon };
    else root.FallInferenceEngine = FallInferenceEngine;
})(typeof window !== 'undefined' ? window : globalThis);
