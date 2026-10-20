(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TargetSampling = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const roundAway = x => Math.sign(x) * Math.floor(Math.abs(x) + 0.5);
  const keyOf = (p, spacing) => roundAway(p[0] / spacing) + ',' + roundAway(p[1] / spacing);
  function evenly(items, limit) {
    const count = Math.min(items.length, Math.max(0, Math.floor(limit)));
    if (!count) return [];
    if (count === 1) return [items[0]];
    return Array.from({ length: count }, (_, i) => items[Math.round(i * (items.length - 1) / (count - 1))]);
  }
  function bodyAt(d, p, k) {
    const theta = d.theta_t_rad?.[k] ?? d.theta_rad[k] - d.phi_rad[k];
    const H = d.xH_m ? [d.xH_m[k], d.yH_m[k]] :
      [d.xB_m[k] + p.l_h * Math.cos(d.theta_rad[k]), d.yB_m[k] + p.l_h * Math.sin(d.theta_rad[k])];
    return { H, theta };
  }
  function firstContacts(points, d, p, tolerance) {
    if (!Number.isFinite(tolerance) || tolerance < 0 || points.some(q => q.length !== 2 || !q.every(Number.isFinite)))
      throw new Error('Contact queries require finite coordinates and a nonnegative tolerance.');
    const result = Array(points.length).fill(NaN);
    let pending = points.map((_, i) => i);
    const tol = Math.max(1e-9, tolerance);
    for (let k = 0; k < d.time_s.length && pending.length; k++) {
      const { H, theta } = bodyAt(d, p, k);
      const c = Math.cos(theta), s = Math.sin(theta);
      pending = pending.filter(i => {
        const dx = points[i][0] - H[0], dy = points[i][1] - H[1];
        const along = dx*c + dy*s, lateral = dx*s - dy*c;
        const a = Math.max(0, along, -p.L-along);
        const b = Math.max(0, Math.abs(lateral)-p.width/2);
        if (a*a + b*b <= tol*tol) { result[i] = k; return false; }
        return true;
      });
    }
    return result;
  }
  function generate(d, p, options = {}) {
    const spacing = options.spacing ?? 0.1;
    const maximum = Math.floor(options.maximum ?? 7000);
    const tolerance = options.tolerance ?? 0.05;
    const band = options.boundaryBand ?? 0.2;
    const margin = options.negativeMargin ?? 0.5;
    if (!(spacing > 0 && maximum >= 3 && tolerance >= 0 && band > 0 && margin > tolerance && p.L > 0 && p.width > 0))
      throw new Error('Sampling requires positive spacing, at least 3 targets, and negative margin greater than tolerance.');
    if (!d.time_s.length) throw new Error('Empty scenario.');
    const pool = { interior: new Map(), boundary: new Map(), negative: new Map() };
    const add = (group, point, source) => {
      const key = keyOf(point, spacing);
      if (!pool[group].has(key)) pool[group].set(key, { point, group, source });
    };
    const frameCount = Math.min(d.time_s.length, Math.max(3, Math.min(80, Math.ceil(maximum / 3))));
    const frames = evenly(Array.from({ length: d.time_s.length }, (_, i) => i), frameCount);
    const longitudinal = Math.max(3, Math.min(80, Math.ceil(p.L / spacing) + 1));
    const lateralCount = Math.max(3, Math.min(9, Math.ceil(p.width / spacing) + 1));
    for (const k of frames) {
      const { H, theta } = bodyAt(d, p, k);
      const e = [Math.cos(theta), Math.sin(theta)], n = [Math.sin(theta), -Math.cos(theta)];
      for (let j = 0; j < longitudinal; j++) {
        const u = j / (longitudinal - 1);
        const mid = [H[0] - p.L*u*e[0], H[1] - p.L*u*e[1]];
        const innerU = (j+0.5)/longitudinal;
        const innerMid = [H[0]-p.L*innerU*e[0],H[1]-p.L*innerU*e[1]];
        const at = offset => [mid[0] + offset*n[0], mid[1] + offset*n[1]];
        for (let z = 0; z < lateralCount; z++) {
          const offset=(-0.75 + 1.5*z/(lateralCount-1))*p.width/2;
          add('interior',[innerMid[0]+offset*n[0],innerMid[1]+offset*n[1]],'body_interior');
        }
        for (const offset of [-band, 0, band]) add('boundary', at(p.width/2+offset), 'right_edge_neighborhood');
        for (const sign of [-1, 1]) add('negative', at(sign*(p.width/2+margin)), 'near_body');
      }
    }
    const groups = ['interior', 'boundary', 'negative'];
    const quota = groups.map((_, i) => Math.floor(maximum/3) + (i < maximum%3 ? 1 : 0));
    const candidates = groups.flatMap((group, i) => evenly([...pool[group].values()], quota[i]*6));
    const contact = firstContacts(candidates.map(r => r.point), d, p, tolerance);
    candidates.forEach((r, i) => { r.contact = contact[i]; });
    const eligible = {
      interior: candidates.filter(r => r.group === 'interior' && Number.isFinite(r.contact)),
      boundary: candidates.filter(r => r.group === 'boundary'),
      negative: candidates.filter(r => r.group === 'negative' && !Number.isFinite(r.contact))
    };
    // Fill only a negative shortage with points outside every recorded body.
    if (eligible.negative.length < quota[2]) {
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (let k = 0; k < d.time_s.length; k++) {
        const { H, theta } = bodyAt(d, p, k);
        for (const u of [0, 1]) for (const sign of [-1, 1]) {
          const x = H[0]-p.L*u*Math.cos(theta)+sign*p.width/2*Math.sin(theta);
          const y = H[1]-p.L*u*Math.sin(theta)-sign*p.width/2*Math.cos(theta);
          minX=Math.min(minX,x); maxX=Math.max(maxX,x); minY=Math.min(minY,y); maxY=Math.max(maxY,y);
        }
      }
      for (let i=0; i<quota[2]*4; i++) {
        const u=i/Math.max(1,quota[2]*4-1);
        eligible.negative.push({ point: [minX-margin, minY+(maxY-minY)*u], group:'negative', source:'far_body', contact:NaN });
      }
    }
    const used = new Set(), chosen = [];
    for (let g=0; g<groups.length; g++) {
      const group = groups[g];
      let count=0;
      const ordered = evenly(eligible[group], quota[g]).concat(eligible[group]);
      for (const r of ordered) {
        const key=keyOf(r.point,spacing);
        if (used.has(key)) continue;
        used.add(key); chosen.push(r); count++;
        if (count >= quota[g]) break;
      }
    }
    const edges=contactEdges(chosen.map(r=>r.point),chosen.map(r=>r.contact),d,p);
    return chosen.map((r,i) => ({
      id:i+1, name:'T'+(i+1), x:r.point[0], y:r.point[1], sampleGroup:r.group,
      sampleSource:r.source, trueContactIdx:r.contact,
      truthLabel:Number.isFinite(r.contact) ? 'CONTACT' : 'NO_CONTACT_IN_RECORD',
      targetSetVersion:'mixed_v2', nearestContactEdge:edges[i]
    }));
  }
  function contactEdges(points, indices, d, p) {
    const labels=['RIGHT','LEFT','FRONT','REAR'];
    return indices.map((k,i)=>{
      if (!Number.isFinite(k)) return 'NONE';
      if (k===0) return 'INITIAL_OVERLAP';
      const {H,theta}=bodyAt(d,p,k), dx=points[i][0]-H[0], dy=points[i][1]-H[1];
      const along=dx*Math.cos(theta)+dy*Math.sin(theta), lateral=dx*Math.sin(theta)-dy*Math.cos(theta);
      const outlong=Math.max(0,along,-p.L-along), outlat=Math.max(0,Math.abs(lateral)-p.width/2);
      const distances=[Math.hypot(outlong,lateral-p.width/2),Math.hypot(outlong,lateral+p.width/2),
        Math.hypot(along,outlat),Math.hypot(along+p.L,outlat)];
      const minimum=Math.min(...distances), near=distances.flatMap((v,j)=>v<=minimum+1e-9?[j]:[]);
      return near.length===1 ? labels[near[0]] : 'CORNER';
    });
  }
  function classify(contactTime, warningTime, horizon, endTime, warmup, threshold, contactEdge = '') {
    if (Number.isFinite(contactTime)) {
      if (contactEdge === 'FRONT') return 'FRONT_CONTACT_IGNORED';
      if (contactTime < warmup) return 'STARTUP_TRUNCATED';
      if (!Number.isFinite(warningTime)) return 'POLYW_NO_HIT';
      return contactTime-warningTime < threshold ? 'BLINDSPOT_REACTION_INSUFFICIENT' : 'REACTION_TIME_SUFFICIENT';
    }
    if (!Number.isFinite(warningTime)) return 'CORRECT_REJECTION';
    if (!Number.isFinite(horizon) || warningTime+horizon > endTime+1e-9) return 'END_TRUNCATED';
    return 'FALSE_POSITIVE';
  }
  return { generate, firstContacts, classify, bodyAt, contactEdges };
});
