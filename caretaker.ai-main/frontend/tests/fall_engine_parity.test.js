/**
 * Parity test: the browser engine must make the SAME decisions as the Python
 * engine on identical pose sequences.
 *
 *   cd backend/VideoMonitoring && python evaluate_fall_engine.py --export-fixtures ../../frontend/tests/fixtures/fall_scenarios.json
 *   node frontend/tests/fall_engine_parity.test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { FallInferenceEngine } = require('../static/js/fall-inference-engine.js');

const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'fall_scenarios.json'), 'utf8'));
let failures = 0;
for (const fx of fixtures) {
    const eng = new FallInferenceEngine({ sensitivity: 'medium', bedZones: fx.bed_zones });
    const got = [];
    for (const f of fx.frames) {
        const r = eng.update(f.t, f.xy, f.conf, f.size);
        for (const e of r.events) got.push({ type: e.type, t: e.t, fall_type: e.fall_type ?? null, severity: e.severity ?? null });
    }
    const want = fx.python_events.map(e => ({ type: e.type, t: e.t, fall_type: e.fall_type ?? null, severity: e.severity ?? null }));
    const same = got.length === want.length && got.every((g, i) =>
        g.type === want[i].type && Math.abs(g.t - want[i].t) < 1e-3 && g.fall_type === want[i].fall_type && g.severity === want[i].severity);
    const label = `${fx.name.padEnd(30)} expect=${fx.expect.padEnd(15)}`;
    if (same) {
        const summary = got.filter(e => e.type !== 'candidate_rejected').map(e => `${e.type}${e.fall_type ? '/' + e.fall_type : ''}@${e.t.toFixed(1)}s`).join(', ') || 'no alerts';
        console.log(`PASS ${label} ${summary}`);
    } else {
        failures++;
        console.log(`FAIL ${label}\n  python: ${JSON.stringify(want)}\n  js    : ${JSON.stringify(got)}`);
    }
}
console.log(`\n${fixtures.length - failures}/${fixtures.length} scenarios identical between Python and JS engines`);
process.exit(failures ? 1 : 0);
