// The 3D view of a run and the realistic picture made from it (needs app.js and three.js, loaded when the view is first opened).
// The 3D massing view: walls with the door and window openings cut out, and a plain roof, from /api/runs/<id>/massing. Illustrative only.
let threeReady = null;
function loadScript(src) { return new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = () => no(new Error('could not load ' + src)); document.head.appendChild(s); }); }
function loadThree() {
  threeReady = threeReady || loadScript('https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js').then(() => loadScript('https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js'));
  return threeReady;
}
let m3 = null, m3run = '';
async function open3d(id, opt) {
  opt = opt || {};
  m3run = id;
  let box = document.getElementById('m3d');
  if (!box) { box = document.createElement('div'); box.id = 'm3d'; document.body.appendChild(box); }
  box.className = 'on'; box.innerHTML = '<div class="bar"><b>3D model</b><span class="small mute" id="m3dmsg">Loading…</span><span class="spacer" style="flex:1"></span><button id="m3dclose" style="background:var(--card);color:var(--accent);border-color:var(--accent)">Close</button></div>';
  $('#m3dclose').onclick = close3d;
  try {
    const [data] = await Promise.all([api(`/api/runs/${id}/massing`), loadThree()]);
    if (!data.floors) throw new Error('no walls were measured for this run yet');
    build3d(box, data, opt);
    if (opt.hideRoof) { $('#m3roof').checked = false; $('#m3roof').onchange({target: $('#m3roof')}); }
  } catch (e) { $('#m3dmsg').textContent = 'Could not show the model: ' + e.message; }
}
function close3d() { const box = document.getElementById('m3d'); if (m3) { cancelAnimationFrame(m3.raf); m3.renderer.dispose(); m3 = null; } if (box) { box.className = ''; box.innerHTML = ''; } }
function build3d(box, d, opt) {
  opt = opt || {};
  const T = THREE, H = d.storey_height_m, scene = new T.Scene(), dark = matchMedia('(prefers-color-scheme: dark)').matches;
  scene.background = new T.Color(dark ? 0x14181f : 0xf3f5f8);
  scene.add(new T.AmbientLight(0xffffff, 0.75)); const sun = new T.DirectionalLight(0xffffff, 0.7); sun.position.set(20, 40, 15); scene.add(sun);
  const mat = (c, o) => new T.MeshLambertMaterial(Object.assign({color: c, side: T.DoubleSide}, o || {}));
  const M = {ext: mat(0xd9cdb8), int: mat(0xece6da), glass: mat(0x4aa3b5, {transparent: true, opacity: 0.45}), door: mat(0x8a5a3a), roof: mat(0xa6513f), slab: mat(0x8f9399)};
  const edge = new T.LineBasicMaterial({color: dark ? 0x000000 : 0x555555, transparent: true, opacity: 0.35});
  const groups = [], roofGroup = new T.Group(); let minx = 1e9, minz = 1e9, maxx = -1e9, maxz = -1e9;
  const box3 = (g, a, b, y0, y1, c, t, m) => { // a segment from a to b along the wall at cross position c, thickness t, from height y0 to y1; m = orient
    if (b - a < 0.005 || y1 - y0 < 0.005) return null;
    const dims = m.o === 'h' ? [b - a, y1 - y0, t] : [t, y1 - y0, b - a], mesh = new T.Mesh(new T.BoxGeometry(...dims), m.mat);
    mesh.position.set(m.o === 'h' ? (a + b) / 2 : c, m.base + (y0 + y1) / 2, m.o === 'h' ? c : (a + b) / 2);
    mesh.add(new T.LineSegments(new T.EdgesGeometry(mesh.geometry), edge)); g.add(mesh); return mesh;
  };
  d.floors.forEach(fl => {
    const g = new T.Group(), base = fl.index * H; groups.push({name: fl.name, g});
    fl.walls.forEach(w => {
      const o = Math.abs(w.x1 - w.x0) >= Math.abs(w.y1 - w.y0) && Math.abs(w.y1 - w.y0) < 1e-6 ? 'h' : (Math.abs(w.x1 - w.x0) < 1e-6 ? 'v' : (Math.abs(w.x1 - w.x0) >= Math.abs(w.y1 - w.y0) ? 'h' : 'v'));
      let a = o === 'h' ? Math.min(w.x0, w.x1) : Math.min(w.y0, w.y1), b = o === 'h' ? Math.max(w.x0, w.x1) : Math.max(w.y0, w.y1); const c = o === 'h' ? w.y0 : w.x0;
      if (o === 'h') { a -= w.t / 2; b += w.t / 2; } // fill the corners
      const m = {o, base, mat: w.external ? M.ext : M.int};
      minx = Math.min(minx, o === 'h' ? a : c); maxx = Math.max(maxx, o === 'h' ? b : c); minz = Math.min(minz, o === 'h' ? c : a); maxz = Math.max(maxz, o === 'h' ? c : b);
      const ops = fl.openings.filter(p => p.parent === w.id).map(p => ({k: p.kind, tall: p.tall, tall_from_above: p.tall_from_above, s: o === 'h' ? Math.min(p.x0, p.x1) : Math.min(p.y0, p.y1), e: o === 'h' ? Math.max(p.x0, p.x1) : Math.max(p.y0, p.y1)})).sort((p, q) => p.s - q.s);
      let cur = a;
      ops.forEach(p => {
        const s = Math.max(p.s, cur), e = Math.min(p.e, b); if (e - s < 0.2) return;
        box3(g, cur, s, 0, H, c, w.t, m);
        if (p.k === 'window') { const sill = p.tall ? 0 : d.sill_m, top = p.tall_from_above ? H : Math.min(d.sill_m + d.window_height_m, H), lo = p.tall_from_above ? d.sill_m : sill; if (!p.tall_from_above) box3(g, s, e, 0, sill, c, w.t, m); if (!p.tall_from_above || true) box3(g, s, e, top, H, c, w.t, m); box3(g, s, e, lo, top, c, 0.04, {o, base, mat: M.glass}); if (p.tall_from_above) box3(g, s, e, 0, d.sill_m, c, w.t, m); }
        else { const top = Math.min(d.door_height_m, H); box3(g, s, e, top, H, c, w.t, m); if (p.k === 'door') box3(g, s, e, 0, top, c, 0.05, {o, base, mat: M.door}); }
        cur = e;
      });
      box3(g, cur, b, 0, H, c, w.t, m);
    });
    if (fl.outline && fl.outline.length >= 3) { // the floor slab: the outline the walls enclose, with a hole for each void (a space named Void has no slab)
      const shape = new T.Shape(fl.outline.map(p => new T.Vector2(p[0], -p[1])));
      (fl.voids || []).forEach(v => { const hole = new T.Path([new T.Vector2(v[0], -v[1]), new T.Vector2(v[2], -v[1]), new T.Vector2(v[2], -v[3]), new T.Vector2(v[0], -v[3])].reverse()); shape.holes.push(hole); });
      const slab = new T.Mesh(new T.ExtrudeGeometry(shape, {depth: 0.25, bevelEnabled: false}), M.slab); slab.rotation.x = -Math.PI / 2; slab.position.y = base - 0.25;
      slab.add(new T.LineSegments(new T.EdgesGeometry(slab.geometry), edge)); g.add(slab);
    }
    scene.add(g);
  });
  // roof: a plain shape over the outline of the ground floor walls
  const r = d.roof, top = d.floors.length * H, ov = r.overhang_m, x0 = r.bounds[0] - ov, z0 = r.bounds[1] - ov, x1 = r.bounds[2] + ov, z1 = r.bounds[3] + ov, lx = x1 - x0, lz = z1 - z0;
  if (r.type === 'flat') { const s = new T.Mesh(new T.BoxGeometry(lx, 0.15, lz), M.slab); s.position.set((x0 + x1) / 2, top + 0.075, (z0 + z1) / 2); roofGroup.add(s); }
  else {
    const alongX = lx >= lz, uL = alongX ? lx : lz, vL = alongX ? lz : lx, half = vL / 2, rise = half * Math.tan(r.pitch_deg * Math.PI / 180), P = (u, v, y) => alongX ? [x0 + u, y, z0 + v] : [x0 + v, y, z0 + u];
    const tri = [], quad = (p, q, s2, t2) => tri.push(...p, ...q, ...s2, ...p, ...s2, ...t2), face = (p, q, s2) => tri.push(...p, ...q, ...s2);
    if (r.type === 'gable') {
      quad(P(0, 0, top), P(uL, 0, top), P(uL, half, top + rise), P(0, half, top + rise)); quad(P(0, vL, top), P(uL, vL, top), P(uL, half, top + rise), P(0, half, top + rise));
      face(P(0, 0, top), P(0, vL, top), P(0, half, top + rise)); face(P(uL, 0, top), P(uL, vL, top), P(uL, half, top + rise));
    } else {
      const ra = Math.min(half, uL / 2), rb = uL - ra;
      quad(P(0, 0, top), P(uL, 0, top), P(rb, half, top + rise), P(ra, half, top + rise)); quad(P(0, vL, top), P(uL, vL, top), P(rb, half, top + rise), P(ra, half, top + rise));
      face(P(0, 0, top), P(0, vL, top), P(ra, half, top + rise)); face(P(uL, 0, top), P(uL, vL, top), P(rb, half, top + rise));
    }
    const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.Float32BufferAttribute(tri, 3)); geo.computeVertexNormals();
    const rm = new T.Mesh(geo, M.roof); rm.add(new T.LineSegments(new T.EdgesGeometry(geo, 20), edge)); roofGroup.add(rm);
  }
  scene.add(roofGroup);
  const ground = new T.Mesh(new T.PlaneGeometry(200, 200), mat(dark ? 0x1c222b : 0xe4e8ee)); ground.rotation.x = -Math.PI / 2; ground.position.set((minx + maxx) / 2, -0.02, (minz + maxz) / 2); scene.add(ground);
  const cx = (minx + maxx) / 2, cz = (minz + maxz) / 2, span = Math.max(maxx - minx, maxz - minz, 6);
  const renderer = new T.WebGLRenderer({antialias: true}); const cv = renderer.domElement; box.insertBefore(cv, null);
  const note = document.createElement('div'); note.className = 'note'; note.innerHTML = d.notes.map(esc).join(' '); box.appendChild(note);
  const camera = new T.PerspectiveCamera(45, 1, 0.1, 500); camera.position.set(cx + span * 0.9, span * 0.8 + top, cz + span * 1.2);
  if (opt.az !== undefined) { const a = +opt.az * Math.PI / 180; const e = opt.el !== undefined ? +opt.el * Math.PI / 180 : Math.atan2(span * 0.6 + top, span * 1.5); camera.position.set(cx + Math.sin(a) * Math.cos(e) * span * 1.7, Math.sin(e) * span * 1.7 + (opt.el !== undefined ? 0 : 0), cz + Math.cos(a) * Math.cos(e) * span * 1.7); }
  const controls = new T.OrbitControls(camera, cv); controls.target.set(cx, top * 0.5, cz); controls.autoRotate = opt.az === undefined; controls.autoRotateSpeed = 1.2;
  const bar = box.querySelector('.bar'); const ctl = document.createElement('span'); ctl.className = 'small';
  ctl.innerHTML = `<button id="m3render" type="button">Make a realistic picture of this view</button> <label style="margin-left:10px"><input type="checkbox" id="m3roof" checked> roof</label> ${groups.map((x, i) => `<label style="margin-left:10px"><input type="checkbox" class="m3fl" data-i="${i}" checked> ${esc(x.name)} floor</label>`).join('')} <label style="margin-left:10px"><input type="checkbox" id="m3spin" ${opt.az === undefined ? 'checked' : ''}> turn slowly</label> <span class="mute" style="margin-left:10px">drag to turn, scroll to zoom</span>`;
  bar.insertBefore(ctl, bar.querySelector('.spacer'));
  const inPoly = (pt, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const a = poly[i], b = poly[j]; if ((a[1] > pt[1]) !== (b[1] > pt[1]) && pt[0] < (b[0] - a[0]) * (pt[1] - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
  // the windows and doors on external walls that face the camera and are inside the picture (a count to hold the picture to; walls in front are not taken into account)
  const visibleOpenings = () => {
    let windows = 0, doors = 0; const v = new T.Vector3();
    d.floors.forEach((fl, fi) => {
      if (!groups[fi].g.visible) return;
      fl.openings.forEach(p => {
        const w = fl.walls.find(q => q.id === p.parent); if (!w || !w.external || p.kind === 'opening') return;
        const mx = (p.x0 + p.x1) / 2, mz = (p.y0 + p.y1) / 2, horiz = Math.abs(w.x1 - w.x0) >= Math.abs(w.y1 - w.y0);
        let n = horiz ? [0, 1] : [1, 0]; const probe = s => horiz ? [mx, mz + s] : [mx + s, mz];
        const outside = s => fl.outline && fl.outline.length > 2 ? !inPoly(probe(s * 0.6), fl.outline) : (horiz ? (mz - cz) * s > 0 : (mx - cx) * s > 0);
        const sign = outside(1) ? 1 : outside(-1) ? -1 : 0; if (!sign) return;
        const nx = horiz ? 0 : sign, nz = horiz ? sign : 0;
        v.set(mx, fi * H + (p.kind === 'window' ? d.sill_m + d.window_height_m / 2 : d.door_height_m / 2), mz);
        if (nx * (camera.position.x - mx) + nz * (camera.position.z - mz) <= 0) return;
        const q = v.clone().project(camera); if (Math.abs(q.x) > 1 || Math.abs(q.y) > 1) return;
        if (p.kind === 'window') windows++; else doors++;
      });
    });
    return {windows, doors};
  };
  $('#m3render').onclick = async () => {
    const b = $('#m3render'), msg = $('#m3dmsg'); b.disabled = true; const spin = $('#m3spin'); controls.autoRotate = false; if (spin) spin.checked = false;
    msg.textContent = 'Making the picture with Muse Image and checking it against this view: 30 to 60 seconds…';
    try {
      renderer.render(scene, camera); const png = await new Promise(ok => cv.toBlob(ok, 'image/png')), vis = visibleOpenings();
      const r = await fetch(`/api/runs/${m3run}/render`, {method: 'POST', body: png, headers: {'X-Visible': JSON.stringify(vis)}}), j = await r.json();
      if (!r.ok) throw new Error(j.error || 'failed');
      const ov = document.createElement('div'); ov.style.cssText = 'position:absolute;inset:60px 0 34px 0;background:var(--bg);display:flex;flex-direction:column;align-items:center;gap:8px;padding:10px;overflow:auto;z-index:5';
      ov.innerHTML = `<img src="${j.url}" alt="a realistic picture of the house" style="max-width:100%;max-height:calc(100% - 60px);border-radius:8px;border:1px solid var(--line)"><div class="small mute" style="max-width:820px;text-align:center">${j.matched === true ? `<b>Checked:</b> the picture shows the same ${j.expected.windows} windows and ${j.expected.doors} doors as this view. ` : j.matched === false ? `<b>Not matching:</b> this view shows ${j.expected.windows} windows and ${j.expected.doors} doors, the picture about ${j.counted.windows} and ${j.counted.doors} (after ${j.attempts} tries). ` : ''}An illustration made by Muse Image from this view. The finishes, proportions and the exact positions of windows are the model's interpretation: it is not to scale, and the bill comes from the measured plans, not from this picture.</div><div><a class="dl" href="${j.url}" download="house.webp">Save the picture</a> <button id="m3back" style="background:var(--card);color:var(--accent);border-color:var(--accent)">Back to the 3D model</button></div>`;
      box.appendChild(ov); $('#m3back').onclick = () => ov.remove(); msg.textContent = 'Illustration made.';
    } catch (e) { msg.textContent = 'Could not make the picture: ' + e.message; } finally { b.disabled = false; }
  };
  $('#m3roof').onchange = e => { roofGroup.visible = e.target.checked; }; $('#m3spin').onchange = e => { controls.autoRotate = e.target.checked; };
  box.querySelectorAll('.m3fl').forEach(el => el.onchange = e => { groups[+e.target.dataset.i].g.visible = e.target.checked; });
  $('#m3dmsg').textContent = `${d.floors.length} floor${d.floors.length > 1 ? 's' : ''}, ${esc(r.type)} roof at ${r.pitch_deg}°`;
  const fit = () => { const w = cv.clientWidth || box.clientWidth, h = cv.clientHeight || 500; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); };
  new ResizeObserver(fit).observe(box); fit();
  m3 = {renderer, raf: 0}; const loop = () => { controls.update(); renderer.render(scene, camera); m3 && (m3.raf = requestAnimationFrame(loop)); }; loop();
}
