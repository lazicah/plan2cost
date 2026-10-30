// Voice input for the new-estimate form (needs app.js).
// Speaking the details: record in the browser, make a 16 kHz mono WAV (the API takes WAV only), send it to the server, fill the form from what was heard.
let rec = null;
function wavFrom(chunks, rate) {
  const n = chunks.reduce((a, c) => a + c.length, 0), pcm = new Int16Array(n); let o = 0;
  for (const c of chunks) for (let i = 0; i < c.length; i++) { const v = Math.max(-1, Math.min(1, c[i])); pcm[o++] = v < 0 ? v * 0x8000 : v * 0x7fff; }
  const buf = new ArrayBuffer(44 + pcm.length * 2), d = new DataView(buf), w = (p, s) => [...s].forEach((ch, i) => d.setUint8(p + i, ch.charCodeAt(0)));
  w(0, 'RIFF'); d.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVE'); w(12, 'fmt '); d.setUint32(16, 16, true); d.setUint16(20, 1, true); d.setUint16(22, 1, true);
  d.setUint32(24, rate, true); d.setUint32(28, rate * 2, true); d.setUint16(32, 2, true); d.setUint16(34, 16, true); w(36, 'data'); d.setUint32(40, pcm.length * 2, true);
  new Int16Array(buf, 44).set(pcm); return new Blob([buf], {type: 'audio/wav'});
}
async function toggleMic() {
  const btn = $('#mic'), msg = $('#voicemsg');
  if (rec) { rec.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const ctx = new AudioContext({sampleRate: 16000}), src = ctx.createMediaStreamSource(stream), node = ctx.createScriptProcessor(4096, 1, 1), chunks = [];
    node.onaudioprocess = e => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    src.connect(node); node.connect(ctx.destination);
    btn.textContent = '⏹ Stop'; msg.textContent = 'Listening… press Stop when you are done.';
    rec = {stop: async () => {
      rec = null; node.disconnect(); src.disconnect(); stream.getTracks().forEach(t => t.stop()); const rate = ctx.sampleRate; await ctx.close();
      btn.textContent = '🎤 Speak the details'; msg.textContent = 'Listening to the recording…';
      try {
        const r = await fetch('/api/voice', {method: 'POST', body: wavFrom(chunks, rate)}), j = await r.json();
        if (!r.ok) throw new Error(j.error || 'could not hear that');
        const i = j.inputs || {};
        if (i.storey_height_m) $('#height').value = i.storey_height_m;
        if (i.roof_type) { formRoof = i.roof_type; document.querySelectorAll('input[name=roof]').forEach(el => { el.checked = el.value === formRoof; }); document.querySelectorAll('.roofcard').forEach(c => c.classList.toggle('on', c.querySelector('input').checked)); }
        if (i.finish_level) { formFinish = i.finish_level; $('#finish').value = formFinish; }
        if (i.pitch_deg) $('#pitch').value = i.pitch_deg;
        if (i.overhang_m) $('#overhang').value = i.overhang_m;
        const set = Object.entries(i).map(([k, v]) => k.replace(/_/g, ' ') + ' ' + v).join(', ');
        msg.innerHTML = 'Heard: <i>“' + esc(j.transcript) + '”</i>. ' + (set ? 'Filled in: ' + esc(set) + '. Please check the fields.' : 'No details were recognised; fill the fields by hand.');
      } catch (e) { msg.textContent = 'Could not use the recording: ' + e.message; }
    }};
  } catch (e) { msg.textContent = 'The microphone could not be used (' + e.message + '). Fill the fields by hand.'; }
}
