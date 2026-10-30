// The console: the new-estimate form, the run view (progress, plans, bill, audits) and the polling that keeps it current. Plain JavaScript, no build step.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const money = n => n == null ? '' : Number(n).toLocaleString(undefined, {maximumFractionDigits: 2});
const NAMES = ['ground', 'first', 'second', 'third', 'fourth'];
let current = null, lastKey = '', mode = 'run';
let formFloors = [{name: 'ground', file: null}];
let formRoof = '', formQuote = null, formFinish = 'standard';

async function api(path, body) {
  const r = await fetch(path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
  return r.json();
}
async function upload(file) {
  const r = await fetch('/api/upload?name=' + encodeURIComponent(file.name), {method: 'POST', body: file});
  return r.json();
}

// ---- the form: floor plans, the storey height, the roof type
const ROOF_SVG = {
  gable: '<svg viewBox="0 0 120 80"><path d="M10 70 V44 L60 14 L110 44 V70 Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M60 14 V70" stroke="currentColor" stroke-width="2" stroke-dasharray="4 4"/></svg>',
  hip: '<svg viewBox="0 0 120 80"><path d="M10 70 V46 L34 22 H86 L110 46 V70 Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M34 22 L22 46 M86 22 L98 46 M34 22 V46 M86 22 V46" stroke="currentColor" stroke-width="2" fill="none"/></svg>',
  flat: '<svg viewBox="0 0 120 80"><path d="M10 70 V30 H110 V70 Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M10 30 V22 H110 V30" fill="none" stroke="currentColor" stroke-width="3"/></svg>'
};
const ROOFS = [['gable', 'Gable', 'Two sloping sides meeting at a ridge, with a vertical triangle at each end.'], ['hip', 'Hip', 'Slopes on all four sides, no vertical end wall at the top.'], ['flat', 'Flat', 'A concrete slab roof, level or nearly so, with a parapet.']];

function renderForm() {
  const rows = formFloors.map((f, i) => `<div class="frow"><select data-i="${i}" class="fname">${NAMES.map(n => `<option ${n === f.name ? 'selected' : ''}>${n}</option>`).join('')}</select>
      <label class="pick ${f.file ? 'set' : ''}"><input type="file" class="ffile" data-i="${i}" accept=".pdf,.png,.jpg,.jpeg"><span>${esc(f.file ? f.file.name : 'Choose the ' + f.name + ' floor plan (PDF or image)')}</span></label>
      ${f.file && f.file.name.toLowerCase().endsWith('.pdf') ? `<input type="number" min="1" value="${f.page || 1}" data-i="${i}" class="fpage" style="width:80px" title="page of the PDF"> <span class="small mute">page</span>` : ''}
      ${formFloors.length > 1 ? `<button class="rm" data-i="${i}" style="background:var(--card);color:var(--bad);border-color:var(--line)">Remove</button>` : ''}</div>`).join('');
  $('#main').innerHTML = `<section class="card form" style="max-width:820px;margin:0 auto"><h2>New estimate</h2>
    <div class="row" style="margin-bottom:6px"><button id="mic" type="button" style="background:var(--card);color:var(--accent);border-color:var(--accent)">🎤 Speak the details</button><span id="voicemsg" class="small mute">Say, for example: "a single storey, three metres floor to floor, hip roof, premium finish". You can check and change the fields afterwards.</span></div>
    <label class="f">1. Floor plans: one for each floor, lowest first</label><div class="floors">${rows}</div>
    ${formFloors.length < 5 ? '<button id="addfloor" style="background:var(--card);color:var(--accent);border-color:var(--accent)">+ Add a floor</button>' : ''}
    <label class="f">2. Storey height (metres)</label>
    <input id="height" type="number" step="0.05" min="2" max="6" value="${$('#height')?.value || 3.0}" style="width:110px"> m
    <div class="help"><b>Storey height</b> is the distance from the top of one floor to the top of the floor above it (floor to floor). It is <b>not</b> the ceiling height, which is lower by the thickness of the slab and the ceiling. If you are not sure, 3.0 m is typical for a house.</div>
    <label class="f">3. Roof type</label>
    <div class="roofs">${ROOFS.map(([k, name, text]) => `<label class="roofcard ${formRoof === k ? 'on' : ''}"><input type="radio" name="roof" value="${k}" ${formRoof === k ? 'checked' : ''}>${ROOF_SVG[k]}<b>${name}</b><span>${text}</span></label>`).join('')}</div>
    <label class="f">4. Finish level</label>
    <select id="finish"><option value="standard" ${formFinish === 'standard' ? 'selected' : ''}>Standard</option><option value="premium" ${formFinish === 'premium' ? 'selected' : ''}>Premium</option></select>
    <div class="help"><b>Standard</b> prices ceramic floor tiles, standard sanitary ware, flush internal doors, plain light fittings and long-span aluminium roofing. <b>Premium</b> prices 600 × 600 porcelain floor tiles, premium sanitary ware, hardwood swing doors, decorative light fittings and stone-coated roof tiles. Everything else costs the same in both.</div>
    <details style="margin-top:12px"><summary class="small mute">More (optional): roof pitch, overhang and a contractor quote to check</summary>
      <div class="row" style="margin-top:8px"><span class="small">Roof pitch</span><input id="pitch" type="number" min="5" max="60" style="width:90px" placeholder="auto"> <span class="small">degrees</span>
      <span class="small" style="margin-left:12px">Overhang</span><input id="overhang" type="number" step="0.05" min="0" max="2" style="width:90px" placeholder="auto"> <span class="small">m</span></div>
      <div style="margin-top:8px"><label class="pick ${formQuote ? 'set' : ''}"><input type="file" id="quote" accept=".pdf,.png,.jpg,.jpeg,.xlsx"><span>${esc(formQuote ? formQuote.name : 'Contractor quote (optional)')}</span></label></div></details>
    <div style="margin-top:16px"><button id="go">Estimate</button> <span id="formmsg" class="small mute"></span></div></section>`;
  document.querySelectorAll('.fname').forEach(el => el.onchange = e => { formFloors[+e.target.dataset.i].name = e.target.value; renderForm(); });
  document.querySelectorAll('.ffile').forEach(el => el.onchange = e => { formFloors[+e.target.dataset.i].file = e.target.files[0]; renderForm(); });
  document.querySelectorAll('.fpage').forEach(el => el.onchange = e => { formFloors[+e.target.dataset.i].page = +e.target.value; });
  document.querySelectorAll('.rm').forEach(el => el.onclick = e => { formFloors.splice(+e.target.dataset.i, 1); renderForm(); });
  const add = $('#addfloor'); if (add) add.onclick = () => { const used = formFloors.map(f => f.name); formFloors.push({name: NAMES.find(n => !used.includes(n)), file: null}); renderForm(); };
  document.querySelectorAll('input[name=roof]').forEach(el => el.onchange = e => { formRoof = e.target.value; document.querySelectorAll('.roofcard').forEach(c => c.classList.toggle('on', c.querySelector('input').checked)); });
  $('#finish').onchange = e => { formFinish = e.target.value; };
  $('#mic').onclick = () => toggleMic();
  $('#quote').onchange = e => { formQuote = e.target.files[0] || null; renderForm(); };
  $('#go').onclick = start;
}
async function start() {
  const msg = t => $('#formmsg').textContent = t;
  if (formFloors.some(f => !f.file)) return msg('Choose a plan for every floor you added.');
  const names = formFloors.map(f => f.name); if (new Set(names).size !== names.length) return msg('Each floor name can be used once.');
  const height = parseFloat($('#height').value); if (!(height >= 2 && height <= 6)) return msg('The storey height must be between 2 and 6 metres.');
  if (!formRoof) return msg('Choose a roof type.');
  $('#go').disabled = true; msg('Uploading…');
  try {
    const floors = [];
    for (const f of formFloors) { const r = await upload(f.file); if (r.error) return msg(r.error); floors.push({name: f.name, file: r.path, page: f.page || 1}); }
    const body = {floors, storey_height_m: height, roof_type: formRoof, pitch_deg: $('#pitch').value, overhang_m: $('#overhang').value, finish_level: formFinish};
    if (formQuote) { const r = await upload(formQuote); if (r.error) return msg(r.error); body.quote = r.path; }
    const r = await api('/api/start', body);
    if (r.error) return msg(r.error);
    mode = 'run'; current = null; lastKey = ''; setTimeout(tick, 1500);
  } finally { $('#go') && ($('#go').disabled = false); }
}

// ---- a run
function turnClass(t) { const r = t.result || {}; return r.error || r.refused ? 'err' : r.paused ? 'pause' : 'ok'; }
function brief(t) {
  const r = t.result || {};
  if (r.error) return '⚠ ' + r.error;
  if (r.refused) return '⚠ Refused: ' + r.refused.join(' ');
  if (r.paused) return 'Paused for you: ' + r.question;
  if (r.answer) return 'You answered: ' + r.answer;
  if (r.floor && r.ext_girth_m != null) return `${r.floor} floor read: ${money(r.ext_girth_m)} m external, ${money(r.int_girth_m)} m internal wall; ${r.doors} doors, ${r.windows} windows (${r.route}, ${r.confidence} confidence)`;
  if (r.total != null) return `Estimate: ${money(r.total)} ${r.currency || ''} (range ${money(r.total_range?.[0])} to ${money(r.total_range?.[1])}), ${Math.round((r.estimated_share || 0) * 100)}% of it estimated from coefficients` + (r.unpriced?.length ? `; ${r.unpriced.length} lines have no rate` : '');
  if (r.filed) return `Filed. Bills: ${(r.bills || []).join(', ')}`;
  if (r.counts && r.flags) return `Quote audited: ${r.flags.length} questions for the contractor`;
  return '';
}
function render(run) {
  const done = run.checklist.filter(c => ['proven', 'assumed'].includes(c.status)).length;
  const inp = run.inputs || {};
  const thumbFor = i => run.thumbs.includes('p' + String(i + 1).padStart(2, '0') + '.jpg') ? `/api/runs/${run.id}/pages/p${String(i + 1).padStart(2, '0')}.jpg` : null;
  const nowFloor = run.now && run.now.args && run.now.args.floor;
  const stopped = run.status === 'paused' ? `<section class="card q"><h2>The run stopped</h2><div class="small">${esc(run.error || 'It ran out of turns.')} Everything so far is saved.</div><button id="resume">Continue the run</button></section>` : '';
  const q = run.pending ? `<section class="card q"><h2>The agent needs you</h2><div>${esc(run.pending.question)}</div><textarea id="ans" placeholder="Your answer"></textarea><button id="answer">Answer and continue</button></section>` : '';
  const progress = `<section class="card"><div class="stages">${run.stages.map(s => `<span class="stage ${s.done ? 'done' : s.active ? 'active' : ''}">${s.done ? '✓ ' : s.active && run.status === 'running' ? '<span class="spin"></span>' : ''}${esc(s.label)}${s.of ? ' ' + s.count + '/' + s.of : ''}</span>`).join('')}</div>
      ${run.now ? `<div class="small" style="margin-top:10px"><span class="spin"></span><b>Working on:</b> <span class="tool">${esc(run.now.tool)}</span> ${esc(Object.values(run.now.args).join(', '))}</div>` : ''}
      ${run.status === 'running' && run.steps && Object.keys(run.steps).length && run.now && ['read_floor', 'read_all_floors'].includes(run.now.tool) ? `<div class="small steps" style="margin-top:8px">${Object.entries(run.steps).filter(([, s]) => s.text !== 'Done').map(([f, s]) => `<div><b>${esc(f)} floor:</b> ${esc(s.text)} <span class="mute" data-since="${s.since}">…</span></div>`).join('')}</div>` : ''}
      <div class="small mute" style="margin-top:8px">Storey height ${esc(inp.storey_height_m)} m, ${esc(inp.roof_type)} roof, ${esc(inp.finish_level || 'standard')} finish${inp.pitch_deg ? ', pitch ' + esc(inp.pitch_deg) + '°' : ''}${inp.overhang_m ? ', overhang ' + esc(inp.overhang_m) + ' m' : ''}</div></section>`;
  const pv = run.preview;
  const reading = pv ? `<section class="card"><h2>Walls measured: ${esc(pv.floor)} floor</h2><img src="/api/runs/${run.id}/${esc(pv.markup)}?v=${pv.walls}" alt="the walls measured" style="width:100%;border:1px solid var(--line);border-radius:8px">
      <div class="small" style="margin-top:6px"><b>${pv.walls} walls, ${money(pv.total_m)} m</b> (external ${money(pv.external_m)}, internal ${money(pv.internal_m)}) by the ${esc(pv.route)} route. Red is external, blue internal. <span class="mute">The model is now reviewing this plan, reading the room names and finding the doors and windows.</span></div></section>`
    : run.now && ['read_floor', 'read_all_floors'].includes(run.now.tool) ? (() => { const i = Math.max(run.floors.findIndex(f => f.name === nowFloor), 0); const t = thumbFor(i);
        return t ? `<section class="card"><h2>Reading ${nowFloor ? 'the ' + esc(nowFloor) + ' floor plan' : 'all the floor plans'}</h2><div class="live"><img src="${t}" alt="the plan being read"></div><div class="small mute" style="margin-top:6px">Finding the wall lines and fixing the scale from the printed dimensions. The measured walls appear here as soon as they are ready.</div></section>` : ''; })() : '';
  const b = run.built, fl = Object.entries(b.floors || {}), w = b.working;
  const tile = (on, big, label) => `<div class="tile ${on ? 'on' : 'wait'}"><b>${on ? big : '…'}</b><span>${label}</span></div>`;
  const tiles = `<section class="card"><h2>Built so far</h2><div class="tiles">
      ${tile(fl.length, fl.map(([f, m]) => money(m.total_m) + ' m').join(' + '), fl.length ? 'wall length measured, ' + fl.map(([f]) => f).join(' + ') : 'walls')}
      ${tile(fl.length, fl.reduce((a, [f, m]) => a + (m.doors || 0) + (m.windows || 0), 0), 'doors and windows found')}
      ${tile(w, w ? money(w.gross_floor_area_m2) + ' m²' : '', 'gross floor area from the plans')}
      ${tile(b.boq, b.boq ? money(b.boq.low / 1e6) + ' to ' + money(b.boq.high / 1e6) + ' M' : '', b.boq ? 'estimated cost range, ' + esc(b.boq.currency) : 'cost range')}</div></section>`;
  const turns = run.turns.length ? run.turns.map((t, i) => `<div class="turn ${turnClass(t)}"><div><span class="tool">${i + 1}. ${esc(t.tool)}</span> <span class="mute small">${esc(t.reason)}</span></div><div class="small">${esc(brief(t))}</div></div>`).join('') : '<div class="empty">Waiting for the first turn…</div>';
  const checklist = run.checklist.map(c => `<tr><td>${esc(c.id)}</td><td>${esc(c.question)}</td><td><span class="pill ${c.status}">${esc(c.status)}</span></td></tr>`).join('');
  const facts = run.facts.map(f => `<tr><td>${esc(f.name)}</td><td class="n">${esc(f.value)} ${esc(f.unit)}</td><td><span class="pill ${f.source === 'assumed' ? 'assumed' : f.source === 'user' ? 'proven' : 'open'}">${esc(f.source)}</span></td><td class="small mute">${esc(f.basis || '')}</td></tr>`).join('');
  const gallery = run.thumbs.length ? `<section class="card"><h2>The floor plans</h2><div class="thumbs">${run.thumbs.map((f, i) => `<a class="thumb ${run.floors[i] && run.floors[i].name === nowFloor ? 'active' : ''}" href="/api/runs/${run.id}/pages/${f}" target="_blank"><img src="/api/runs/${run.id}/pages/${f}" alt="floor ${i + 1}">${esc(run.floors[i] ? run.floors[i].name : '')}</a>`).join('')}</div></section>` : '';
  const bills = (B) => { const S = B.structure, out = []; let g = '';
    for (const n of [...new Set(B.items.map(i => i.bill))].sort((a, b) => a - b)) { const grp = (S.groups.find(x => x[1].includes(n)) || ['OTHER'])[0];
      out.push({n, name: S.bills[n] || 'Other items', group: grp, first: grp !== g, items: B.items.filter(i => i.bill === n)}); g = grp; } return out; };
  const boq = run.boq ? (() => { const B = run.boq, parts = bills(B); const sub = items => items.reduce((a, i) => a + (i.amount || 0), 0);
    return `<section class="card"><h2>Bill of quantities (budget estimate)</h2>
      <div class="row"><span class="big">${money(B.total)} ${esc(B.currency)}</span><span class="mute">range ${money(B.total_low)} to ${money(B.total_high)}</span><span class="small">${Math.round(B.estimated_share * 100)}% of the cost is estimated from coefficients</span></div>
      <div class="small mute" style="margin-top:4px">Rates: ${esc(B.rates?.label || '')}. Edit them in data/rates.json.${B.rates?.tier_notes && Object.keys(B.rates.tier_notes).length ? ` <span class="mute">What the finish level changes: ${Object.entries(B.rates.tier_notes).map(([k, v]) => esc(k.replace(/_/g, ' ')) + ' (' + esc(v[B.rates.tier]) + ')').join('; ')}.</span>` : ''}</div>
      <table style="margin-top:10px"><tr><th>BESMM4</th><th>Description</th><th>Basis</th><th>Unit</th><th class="n">Qty</th><th class="n">Range</th><th class="n">Rate</th><th class="n">Amount</th></tr>
      ${parts.map(b => `${b.first ? `<tr><td colspan="8" style="background:var(--chip)"><b>${esc(b.group)}</b></td></tr>` : ''}<tr><td colspan="8"><b>BILL No. ${String(b.n).padStart(2, '0')} — ${esc(b.name.toUpperCase())}</b></td></tr>
        ${b.items.map(i => `<tr><td class="small mute">${esc(i.besmm || '')}</td><td>${esc(i.description)}</td><td><span class="tag ${esc(i.basis)}">${esc(i.basis)}</span></td><td>${esc(i.unit)}</td><td class="n">${money(i.qty)}</td>
          <td class="n small mute">${i.basis === 'estimated' ? money(i.qty_low) + ' to ' + money(i.qty_high) : ''}</td><td class="n">${i.rate ? money(i.rate) : '<span class="assumed">no rate</span>'}</td><td class="n">${i.amount ? money(i.amount) : ''}</td></tr>`).join('')}
        <tr style="background:var(--chip)"><td colspan="7" class="small">Bill No. ${String(b.n).padStart(2, '0')} — ${esc(b.name)} carried to summary</td><td class="n"><b>${money(sub(b.items))}</b></td></tr>`).join('')}
      <tr><td colspan="7"><b>Total (priced lines)</b></td><td class="n"><b>${money(B.total)}</b></td></tr></table>
      ${B.coverage ? `<p class="small"><b>Coverage.</b> ${esc(B.coverage.statement)}</p>` : ''}
      ${B.unpriced?.length ? `<p class="small assumed">No rate yet for ${B.unpriced.length} lines, so they are not in the total. Add a rate to include them: ${B.unpriced.map(esc).join(', ')}</p>` : ''}
      ${run.assumptions.length ? `<details><summary class="small mute">${run.assumptions.length} assumptions and open checks</summary><ul class="small">${run.assumptions.map(a => `<li><b>${esc(a.name)}</b> = ${esc(a.value)}: ${esc(a.basis)}</li>`).join('')}</ul></details>` : ''}</section>`; })() : '';
  const mat = run.materials ? (() => { const M = run.materials; let g = '';
    return `<section class="card"><h2>Bill of materials and labour</h2>
      <div class="row"><span class="big">${money(M.total)} ${esc(run.boq?.currency || '')}</span><span class="mute">range ${money(M.total_low)} to ${money(M.total_high)}</span></div>
      <div class="small mute" style="margin-top:4px">Materials and labour for the work above, from the author's own practice (cement bags per m³, planks per m², labour rates). It leaves out preliminaries, overheads, profit and VAT.</div>
      ${M.sections.map(s => { const head = s.group !== g ? `<div style="margin-top:12px"><b>${esc(s.group)}</b></div>` : ''; g = s.group;
        return `${head}<details><summary><b>BILL No. ${String(s.bill).padStart(2, '0')} — ${esc(s.name)}</b> <span class="mute small">${money(s.amount)}</span></summary>
          <table class="small"><tr><th>Item</th><th>Material / description</th><th class="n">Qty</th><th>Unit</th><th class="n">Rate</th><th class="n">Amount</th></tr>
          ${s.subs.map(sb => `<tr><td colspan="6" style="background:var(--chip)"><i>${esc(sb.name)}</i></td></tr>${sb.lines.map(l => `<tr><td class="mute">${esc(l.no)}</td><td>${esc(l.description)}</td><td class="n">${money(l.qty)}</td><td>${esc(l.unit)}</td><td class="n">${money(l.rate)}</td><td class="n">${money(l.amount)}</td></tr>`).join('')}
            <tr><td></td><td class="small"><b>SUBTOTAL – ${esc(sb.name)}</b></td><td colspan="3"></td><td class="n"><b>${money(sb.amount)}</b></td></tr>`).join('')}
          ${s.carried.length ? `<tr><td colspan="6" style="background:var(--chip)"><i>Items carried at the BoQ rate</i></td></tr>${s.carried.map(l => `<tr><td class="mute">${esc(l.no)}</td><td>${esc(l.description)}</td><td class="n">${money(l.qty)}</td><td>${esc(l.unit)}</td><td class="n">${money(l.rate)}</td><td class="n">${money(l.amount)}</td></tr>`).join('')}` : ''}
          </table></details>`; }).join('')}</section>`; })() : '';
  const models = Object.entries(run.models || {}).map(([f, m]) => `<section class="card"><h2>Walls found: ${esc(f)} floor</h2><div class="small">${m.walls} walls, ${money(m.total_m)} m (external ${money(m.external_m)}, internal ${money(m.internal_m)}) by the ${esc(m.route)} route, ${esc(m.confidence)} confidence.</div>
      ${(m.issues || []).length ? `<ul class="small">${m.issues.map(i => `<li class="${i.severity === 'error' ? 'escalated' : 'assumed'}">${esc(i.message)}</li>`).join('')}</ul>` : '<div class="small proven">All checks passed.</div>'}
      <a href="/api/runs/${run.id}/${esc(m.markup)}?v=${run.turn}" target="_blank"><img src="/api/runs/${run.id}/${esc(m.markup)}?v=${run.turn}" alt="annotated plan" style="width:100%;border:1px solid var(--line);border-radius:8px;margin-top:8px"></a></section>`).join('');
  const view3d = Object.keys(run.models || {}).length ? `<section class="card row"><button id="open3d">View the house in 3D</button><span class="small mute">An illustrative model from the walls and openings that were measured. It is not used for any quantity.</span></section>` : '';
  const downloads = run.files.length ? `<section class="card"><h2>Files</h2>${run.files.map(f => `<a class="dl" href="/api/runs/${run.id}/files/${esc(f)}">${esc(f.replace(/_/g, ' ').replace('.xlsx', ' (Excel)').replace('.pdf', ' (PDF)').replace('.json', ' (data)'))}</a>`).join('')}
      <div class="small mute" style="margin-top:6px">A budget estimate has estimated lines, so no bill for tender is made from it: quantities must be measured from full drawings first.</div></section>` : '';
  const audit = run.audit ? `<section class="card"><h2>Contractor quote audit</h2><div class="small">${run.audit.lines} quote lines, ${run.audit.matched} matched to our BoQ. On the matched lines the quote totals ${money(run.audit.quote_total_on_matched_lines)} against ${money(run.audit.our_total_on_matched_lines)} at your rates; priced work the quote leaves out is about ${money(run.audit.our_priced_work_not_in_quote)}.</div>
      <table class="small"><tr><th>Line</th><th>What we found</th><th>What to ask</th></tr>${run.audit.flags.map(f => `<tr><td>${esc(f.line)}</td><td class="${f.severity === 'error' ? 'escalated' : f.severity === 'warn' ? 'assumed' : ''}">${esc(f.message)}</td><td class="mute">${esc(f.ask)}</td></tr>`).join('')}</table></section>` : '';
  $('#main').innerHTML = `<section class="card row"><span class="pill ${run.status}">${esc(run.status.replace('_', ' '))}</span><span>Turn ${run.turn}</span><span class="spacer"></span><span class="small">${done}/${run.checklist.length} checklist items settled</span></section>
    ${progress}${stopped}${reading}${tiles}${view3d}${q}${gallery}
    <div class="cols"><section class="card"><h2>What the agent did</h2>${turns}</section>
      <div style="display:grid;gap:16px;align-content:start"><section class="card"><h2>Checklist</h2><table>${checklist}</table></section>
      <section class="card"><h2>Facts and where they came from</h2><table><tr><th>Name</th><th class="n">Value</th><th>Source</th><th>Basis</th></tr>${facts || '<tr><td class="mute">None yet</td></tr>'}</table></section></div></div>${models}${boq}${mat}${downloads}${audit}`;
  const o3 = $('#open3d'); if (o3) o3.onclick = () => open3d(run.id);
  const rs = $('#resume'); if (rs) rs.onclick = async () => { rs.disabled = true; await api(`/api/runs/${run.id}/resume`, {}); };
  const btn = $('#answer'); if (btn) btn.onclick = async () => { btn.disabled = true; await api(`/api/runs/${run.id}/answer`, {answer: $('#ans').value}); };
}

async function tick() {
  const runs = await api('/api/runs');
  const sel = $('#runs');
  sel.innerHTML = runs.map(r => `<option value="${r.id}">${r.id} · ${r.status} · ${(r.floors || []).length} floors</option>`).join('');
  if (mode === 'form') return;
  if (!current && runs.length) current = runs[0].id;
  if (current) sel.value = current;
  if (!current) { mode = 'form'; return renderForm(); }
  const run = await api('/api/runs/' + current);
  if (run.error && !run.stages) return;
  const key = JSON.stringify([run.status, run.turn, run.pending, run.facts.length, run.now, run.files, run.thumbs.length, run.built, run.preview, run.steps, run.error]) + document.activeElement?.id;
  if (key !== lastKey) { if (document.activeElement?.id !== 'ans') render(run); lastKey = key; }
}
$('#runs').onchange = e => { current = e.target.value; mode = 'run'; lastKey = ''; tick(); };
$('#newbtn').onclick = () => { mode = 'form'; formFloors = [{name: 'ground', file: null}]; formRoof = ''; formQuote = null; formFinish = 'standard'; renderForm(); };
async function showLog() { if ($('#logbox').open) $('#log').textContent = (await api('/api/log')).tail || '(empty)'; }
