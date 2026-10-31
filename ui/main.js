// Start-up, run last: open a 3D view (#3d-<id>) or a run (#run-<id>) from a link, then poll the server (needs app.js, voice.js and view3d.js).
if (/^#3d-\d{8}-\d{6}(-noroof)?(-az\d+)?(-el\d+)?$/.test(location.hash)) open3d(location.hash.slice(4, 19), {hideRoof: location.hash.includes('-noroof'), az: (location.hash.match(/-az(\d+)/) || [])[1], el: (location.hash.match(/-el(\d+)/) || [])[1]});  // a link straight to the 3D view of a run: -noroof hides the roof, -az<degrees> sets the viewing direction, -el<degrees> its height
const linked = location.hash.match(/^#run-(\d{8}-\d{6})$/);
if (linked) current = linked[1];  // a link to a run: #run-<id>
tick(); setInterval(tick, 2000); setInterval(showLog, 3000);
  setInterval(() => document.querySelectorAll('[data-since]').forEach(el => { const s = Math.max(0, Math.round(Date.now() / 1000 - Number(el.dataset.since))); el.textContent = '(' + (s >= 60 ? Math.floor(s / 60) + ' min ' + (s % 60) + ' s' : s + ' s') + ')'; }), 1000);
