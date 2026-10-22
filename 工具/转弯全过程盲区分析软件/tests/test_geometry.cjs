const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
for (const [, source] of scripts) new vm.Script(source);
const start = html.indexOf('    function sweptStepHull(');
const end = html.indexOf('    function generateBoundaryTargets(', start);
assert(start >= 0 && end > start);
const context = vm.createContext({});
vm.runInContext('const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));\n' + html.slice(start, end), context);

let checks = 0;
function check(condition, name) {
  assert(condition, name);
  checks++;
}
const crossed = [{ H: [0, 0], T: [2, 2] }, { H: [2, 0], T: [0, 2] }];
check(context.pointInSweptSegmentsTol([1, 1], crossed, 0), 'crossed-step interior retained');
check(!context.pointInSweptSegmentsTol([3, 1], crossed, 0), 'outside crossed step');
const stationary = [{ H: [3, 4], T: [7, 4] }, { H: [3, 4], T: [7, 4] }];
check(context.pointInSweptSegmentsTol([5, 4], stationary, 0), 'degenerate edge retained');
check(context.pointInSweptSegmentsTol([5, 4.04], stationary, 0.05), 'distance tolerance included');
check(!context.pointInSweptSegmentsTol([5, 4.06], stationary, 0.05), 'distance tolerance excluded');
const point = [{ H: [3, 4], T: [3, 4] }, { H: [3, 4], T: [3, 4] }];
check(context.pointInSweptSegmentsTol([3, 4], point, 0), 'degenerate point retained');
check(!context.pointInSweptSegmentsTol([0, 0], point, 0), 'no origin fallback');
for (let t = 0; t <= 1.001; t += 0.1) {
  for (let u = 0; u <= 1.001; u += 0.05) {
    const p = [(1 - u) * 2 * t + u * 2 * (1 - t), 2 * u];
    check(context.pointInSweptSegmentsTol(p, crossed, 0), 'linear edge interpolation covered');
  }
}
if (process.argv[2]) {
  const fixtures = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  for (const fixture of fixtures) {
    const edges = fixture.H.map((H, i) => ({ H, T: fixture.T[i] }));
    fixture.queries.forEach((p, i) => {
      check(context.pointInSweptSegmentsTol(p, edges, fixture.tolerance) === fixture.expected[i],
        `MATLAB/web agreement: ${fixture.name}, query ${i}`);
    });
  }
}
console.log(`PASSED: ${checks} JavaScript geometry checks; inline scripts parse successfully.`);
const logDir = path.join(__dirname, '..', 'logs');
fs.mkdirSync(logDir, { recursive: true });
const logPath = path.join(logDir, `js_geometry_${Date.now()}.json`);
fs.writeFileSync(logPath, JSON.stringify({
  method: 'segment_convex_union', passed: checks,
  matlabFixtures: process.argv[2] ? path.resolve(process.argv[2]) : null,
  browserUiTested: false, createdAt: new Date().toISOString(),
}, null, 2));
console.log(`Report: ${logPath}`);
