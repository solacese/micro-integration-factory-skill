(function () {
  'use strict';
  var byId = function (id) { return document.getElementById(id); };
  var input = byId('input'), messages = byId('messages'), send = byId('send');
  var history = [], project = null, previousCore = '', busy = false, endpoint = '', tick = null, controller = null, started = 0;
  var session = 0;
  function state(label, note, kind) { byId('status').textContent = label; byId('status-note').textContent = note; byId('state').className = 'state ' + (kind || ''); }
  function append(role, text, error) {
    var message = document.createElement('div'); message.className = 'message ' + role + (error ? ' error' : '');
    var who = document.createElement('div'); who.className = 'who'; who.textContent = role === 'user' ? 'YOU' : 'MI FACTORY';
    var body = document.createElement('div'); body.className = 'body';
    String(text).split(/(```[\s\S]*?```)/g).forEach(function (part) {
      if (part.indexOf('```') === 0) { var pre = document.createElement('pre'); pre.textContent = part.replace(/^```[^\n]*\n?/, '').replace(/```$/, ''); body.appendChild(pre); }
      else {
        part.split(/(https?:\/\/[^\s<>()\[\]]+)/g).forEach(function (value) {
          if (/^https?:\/\//.test(value)) { var a = document.createElement('a'); a.href = value; a.textContent = value; a.target = '_blank'; a.rel = 'noopener noreferrer'; body.appendChild(a); }
          else body.appendChild(document.createTextNode(value));
        });
      }
    });
    message.append(who, body); messages.appendChild(message); messages.scrollTop = messages.scrollHeight;
  }
  function ui(value) { busy = value; input.disabled = value; send.disabled = value || !endpoint; byId('messages').setAttribute('aria-busy', String(value)); }
  function timer() { var seconds = Math.floor((Date.now() - started) / 1000); byId('timer').textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0') + ' elapsed'; }
  function clearArtifact() { project = null; byId('download').disabled = true; byId('details').textContent = ''; byId('file-status').textContent = 'Your integration’s business logic'; }
  async function request() {
    if (busy || !endpoint) return;
    var thisSession = session; ui(true); clearArtifact();
    state('Building your v1', 'Looking up references and writing Core.java…', 'working');
    started = Date.now(); timer(); tick = setInterval(timer, 1000);
    controller = new AbortController(); var timeout = setTimeout(function () { if (controller) controller.abort(); }, 240000);
    try {
      var response = await fetch(endpoint + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ messages: history.slice(-16), coreJava: previousCore }) });
      var data = await response.json();
      if (!response.ok) throw new Error(data.error || data.detail || 'The build service is unavailable.');
      if (thisSession !== session) return;
      append('assistant', data.content || 'Please describe your expected input and output.'); history.push({ role: 'assistant', content: data.content || 'Please describe your expected input and output.' });
      if (data.project) {
        project = data.project; previousCore = project.coreJava || '';
        if (!/^[a-f0-9]{64}$/.test(project.sha256 || '') || !project.zipBase64) throw new Error('The build returned an incomplete download.');
        state('MI v1 generated', 'Core.java is ready. Download the project to build and verify it.', 'ready');
        byId('file-status').textContent = previousCore.split('\n').length + ' lines · Java 17';
        byId('details').textContent = (data.sources || []).length + ' references checked · ' + project.contractExamples + ' contract examples';
        byId('download').disabled = false;
        byId('download-note').textContent = 'Includes installation and verification scripts. Generation does not mean the code has been compiled.';
      } else state('One detail needed', 'Reply in the chat to finish your v1.');
    } catch (error) {
      if (thisSession !== session) return;
      clearArtifact(); state('Build interrupted', 'Your request is kept in this chat. Retry when you’re ready.');
      append('assistant', error.name === 'AbortError' ? 'This build timed out. Please retry with a more focused request.' : error.message, true);
      var retry = document.createElement('button'); retry.className = 'quiet'; retry.type = 'button'; retry.textContent = 'Retry build';
      retry.onclick = function () { retry.remove(); request(); }; messages.appendChild(retry);
    } finally {
      clearTimeout(timeout); if (thisSession === session) { clearInterval(tick); controller = null; ui(false); input.focus(); }
    }
  }
  byId('form').addEventListener('submit', function (event) { event.preventDefault(); var text = input.value.trim(); if (!text || busy || !endpoint) return; append('user', text); history.push({ role: 'user', content: text }); input.value = ''; input.style.height = 'auto'; request(); });
  input.addEventListener('input', function () { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; });
  input.addEventListener('keydown', function (event) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); byId('form').requestSubmit(); } });
  byId('reset').addEventListener('click', function () { session++; if (controller) controller.abort(); controller = null; clearInterval(tick); history = []; previousCore = ''; clearArtifact(); messages.replaceChildren(); byId('timer').textContent = ''; input.value = ''; ui(false); state('Ready when you are', 'Start with an input, the behavior you need, and an expected output.'); welcome(); input.focus(); });
  byId('download').addEventListener('click', async function () {
    if (!project) return;
    try {
      var bytes = Uint8Array.from(atob(project.zipBase64), function (c) { return c.charCodeAt(0); });
      var digest = await crypto.subtle.digest('SHA-256', bytes);
      var hex = Array.from(new Uint8Array(digest)).map(function (x) { return x.toString(16).padStart(2, '0'); }).join('');
      if (hex !== project.sha256) throw new Error('Download verification failed. Please generate again.');
      var url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' })); var a = document.createElement('a');
      a.href = url; a.download = (project.filename || 'mi-v1.zip').replace(/[^a-zA-Z0-9_.-]/g, '-'); a.click(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    } catch (error) { state('Download failed', error.message); }
  });
  function welcome() { append('assistant', 'What should your MI do? Tell me what comes in and what should come out. An example input and output is enough to start.'); }
  async function connect() {
    ui(false); send.disabled = true;
    try {
      var config = await fetch('demo-config.json', { cache: 'no-store' }); if (!config.ok) throw new Error('Missing service configuration');
      var data = await config.json(); var parsed = new URL(data.apiBaseUrl);
      if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname))) throw new Error('Invalid service URL');
      endpoint = parsed.href.replace(/\/$/, '');
      var health = await fetch(endpoint + '/health', { signal: AbortSignal.timeout(15000) }); if (!health.ok) throw new Error('Service unavailable');
      byId('connection').textContent = 'AI Core connected'; byId('connection-dot').style.background = 'var(--green)'; ui(false);
    } catch (error) { endpoint = ''; byId('connection').textContent = 'Build service unavailable'; state('Service unavailable', 'The build service is temporarily unavailable. Please reload to retry.'); send.disabled = true; }
  }
  welcome(); connect();
})();
