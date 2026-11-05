(function () {
  'use strict';
  var byId = function (id) { return document.getElementById(id); };
  var input = byId('input'), messages = byId('messages'), send = byId('send');
  var templateButtons = document.querySelectorAll('[data-template]');
  var templatePrompts = {
    anonymization: 'Read customer activity JSON from a Solace queue. Keep only eventType and productCategory, and publish the result to activity/anonymized.',
    transformation: 'Read order JSON from a Solace queue. Convert orderId and total to XML and publish it to orders/transformed.',
    target: 'Consume events from [Solace queue] and deliver them to [external system or API]. Acknowledge each message after successful delivery.',
    source: 'Read events from [external system or API] and publish them to [Solace topic]. Load credentials from configuration.'
  };
  var history = [], project = null, previousCore = '', previousGo = '', busy = false, endpoint = '', tick = null, controller = null, started = 0;
  var session = 0, confirmationToken = '', pendingJob = null;
  var jobStorageKey = 'mi-factory-validation-v1';
  function forgetJob(){try{sessionStorage.removeItem(jobStorageKey);}catch(error){/* Storage may be disabled. */}}
  function rememberJob(job){try{sessionStorage.setItem(jobStorageKey,JSON.stringify(job));}catch(error){/* The current session can still finish. */}}
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
  function ui(value) {
    busy = value;
    input.disabled = value;
    send.disabled = value;
    templateButtons.forEach(function (button) { button.disabled = value; });
    messages.setAttribute('aria-busy', String(value));
  }
  function timer() { var seconds = Math.floor((Date.now() - started) / 1000); byId('timer').textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0') + ' elapsed'; }
  function clearArtifact() { project = null; byId('performance').hidden=true; byId('performance').replaceChildren(); ['download','download-go','download-config','download-tests'].forEach(function(id){byId(id).disabled=true;}); byId('details').textContent = ''; byId('file-status').textContent = 'One behavior. Two complete runtimes.'; }
  function clearConfirmationActions() { messages.querySelectorAll('.confirm-actions').forEach(function (item) { item.remove(); }); }
  function submit(text) {
    if (!text || busy) return;
    pendingJob=null; forgetJob();
    clearConfirmationActions(); append('user', text); history.push({ role: 'user', content: text });
    input.value = ''; input.style.height = 'auto'; request();
  }
  function confirmService() {
    var actions = document.createElement('div'); actions.className = 'confirm-actions';
    var yes = document.createElement('button'); yes.type = 'button'; yes.className = 'confirm-yes'; yes.textContent = 'Yes, build and test both';
    yes.onclick = function () { submit('yes'); };
    var change = document.createElement('button'); change.type = 'button'; change.className = 'quiet'; change.textContent = 'Change service';
    change.onclick = function () { clearConfirmationActions(); input.placeholder = 'Which service or API should I use instead?'; input.focus(); };
    actions.append(yes, change); messages.lastElementChild.appendChild(actions); messages.scrollTop = messages.scrollHeight;
  }
  async function request() {
    if (busy) return;
    var thisSession = session; ui(true); clearArtifact();
    var approving = confirmationToken && /^(yes|confirm|proceed|generate|oui|correct)/i.test(history[history.length - 1].content.trim());
    state(approving ? 'Building your v1' : 'Checking the fit', approving ? 'Writing Java and Go, then bundling both MIs…' : 'Checking Integration Hub, requirements and official API docs…', 'working');
    started = pendingJob && pendingJob.clientStarted || Date.now(); timer(); tick = setInterval(timer, 1000);
    controller = new AbortController(); var timeout = setTimeout(function () { if (controller) controller.abort(); }, 240000);
    try {
      var apiBase = endpoint || await loadEndpoint(controller.signal);
      if (thisSession !== session) return;
      endpoint = apiBase;
      var data;
      if (pendingJob) data = pendingJob;
      else {
      var response = await fetch(endpoint + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ messages: history.slice(-16), coreJava: previousCore, coreGo:previousGo, confirmationToken: confirmationToken }) });
      data = await response.json();
      if (!response.ok) throw new Error(data.error || data.detail || 'The build service is unavailable.');
      if (data.status === 'build_failed') throw new Error(data.content || 'The build could not finish. Please retry this request.');
      }
      if (thisSession !== session) return;
      if (data.status === 'validating') {
        pendingJob = data; pendingJob.clientStarted = pendingJob.clientStarted || started; rememberJob(pendingJob);
        append('assistant', data.content || 'Both cores are written. Building and benchmarking both runtimes before enabling downloads.');
        clearTimeout(timeout);
        data = await waitForValidation(data, thisSession);
        if (thisSession !== session) return;
      }
      pendingJob = null;
      if (data.status === 'validation_failed') {
        if(data.performance) renderPerformance(data.performance);
        state('Validation did not pass', data.content || 'Downloads remain locked. Refine your request or retry.');
        append('assistant', data.content || 'Validation did not pass. Downloads remain locked.', true);
        var rebuild=document.createElement('button');rebuild.className='quiet';rebuild.type='button';rebuild.textContent=history.length&&confirmationToken?'Rebuild and test':'Start a new MI';rebuild.onclick=function(){rebuild.remove();if(history.length&&confirmationToken)request();else byId('reset').click();};messages.appendChild(rebuild);
        return;
      }
      append('assistant', data.content || 'Please describe your expected input and output.'); history.push({ role: 'assistant', content: data.content || 'Please describe your expected input and output.' });
      if (data.status === 'awaiting_confirmation') {
        confirmationToken = data.confirmationToken || '';
        if (!confirmationToken) throw new Error('The service confirmation could not be prepared. Please retry.');
        state('Confirm the fit and API', 'Review the custom scope and API, then choose Yes to build.');
        byId('details').textContent = 'Describe → confirm → download'; confirmService();
      }
      else if (data.project) {
        confirmationToken = '';
        project = data.project; previousCore = project.coreJava || ''; previousGo=project.coreGo||'';
        var downloads=[project.java||project,project.go,project.configuration];
        downloads.forEach(function(item){if(!item||!/^[a-f0-9]{64}$/.test(item.sha256||'')||!item.downloadUrl)throw new Error('The build returned an incomplete download.');});
        state('Both runtimes passed', 'Build, contract and 1,000 messages/s checks passed.', 'ready');
        renderPerformance(data.performance || project.performance);
        byId('file-status').textContent = 'Java / SMF · Go / ' + String(project.goTransport || '').toUpperCase();
        byId('details').textContent = (data.sources || []).length + ' references checked · ' + project.contractExamples + ' contract examples';
        ['download','download-go','download-config'].forEach(function(id){byId(id).disabled=false;});
        if(project.tests && /^[a-f0-9]{64}$/.test(project.tests.sha256||'') && project.tests.downloadUrl) byId('download-tests').disabled=false;
        else byId('download-tests').title='Start a new MI to generate its test kit.';
        byId('download-note').textContent = 'Choose Java MDK or Go, complete the shared YAML, and download the test kit for SDK Perf, samples and measured results.';
      } else {
        confirmationToken = '';
        var decisions = {
          reuse:['Use an existing integration','Open the recommended Hub entry. Describe any remaining custom gap here.'],
          architecture_review:['Architecture review needed','Review the requirements and suggested approach before building.'],
          clarify:['Check the fit first','Answer the question in the chat.'],
          flow_limit:['Start a new MI','Five turns reached. Choose New MI for a fresh draft.']
        };
        var decision=decisions[data.status]||['One detail needed','Reply in the chat to finish your v1.'];
        state(decision[0],decision[1]);
        if(data.qualification)byId('details').textContent='Fit checked · generation paused';
      }
    } catch (error) {
      if (thisSession !== session) return;
      clearArtifact(); state('Build interrupted', 'Your request is kept in this chat. Retry when you’re ready.');
      append('assistant', error.name === 'AbortError' ? 'This build timed out. Please retry with a more focused request.' : error.message, true);
      var retry = document.createElement('button'); retry.className = 'quiet'; retry.type = 'button'; retry.textContent = 'Retry build';
      retry.onclick = function () { retry.remove(); request(); }; messages.appendChild(retry);
    } finally {
      clearTimeout(timeout); if (thisSession === session) { clearInterval(tick); controller = null; ui(false); input.focus({ preventScroll: true }); }
    }
  }
  async function waitForValidation(job, currentSession) {
    var deadline = Date.now() + 20 * 60 * 1000;
    state('Building and benchmarking', 'An isolated worker will test both runtimes. This can take several minutes.', 'working');
    while (Date.now() < deadline && currentSession === session) {
      await new Promise(function(resolve, reject) {
        var signal=controller.signal;
        function abort(){clearTimeout(id);reject(new DOMException('Aborted','AbortError'));}
        var id=setTimeout(function(){signal.removeEventListener('abort',abort);resolve();},3500);
        signal.addEventListener('abort',abort,{once:true});
      });
      var response=await fetch(endpoint+'/validation/status', {method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
        body:JSON.stringify({jobId:job.jobId, validationToken:job.validationToken})});
      var data=await response.json();
      if(!response.ok) throw new Error(data.error || data.detail || 'Validation status unavailable.');
      if(data.status!=='validating') return data;
      state('Building and benchmarking', data.note || 'Running isolated validation…', 'working');
    }
    throw new Error('Validation has not completed. Downloads remain locked.');
  }
  function renderPerformance(report) {
    var panel=byId('performance');panel.replaceChildren();panel.hidden=false;
    var heading=document.createElement('h3');heading.textContent='MEASURED · 1,000 MSG/S TARGET';panel.appendChild(heading);
    var table=document.createElement('table');
    function row(values, header) {var tr=document.createElement('tr');values.forEach(function(value){var cell=document.createElement(header?'th':'td');cell.textContent=value;tr.appendChild(cell);});table.appendChild(tr);}
    var runtimes=report.runtimes||{}, java=runtimes.java||{}, go=runtimes.go||{};
    row(['', 'JAVA', 'GO'],true);
    function fmt(value, suffix){return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:1})+suffix:'—';}
    function latency(item,key){return (item.latencyMs||{})[key];}
    row(['Transport',String(java.transport||'smf').toUpperCase(),String(go.transport||'—').toUpperCase()]);
    row(['Delivered / s',fmt(java.achievedRate,''),fmt(go.achievedRate,'')]);
    row(['Peak 1 sec / s',fmt(java.peakOneSecondRate,''),fmt(go.peakOneSecondRate,'')]);
    row(['p95 latency',fmt(latency(java,'p95'),' ms'),fmt(latency(go,'p95'),' ms')]);
    row(['p99 latency',fmt(latency(java,'p99'),' ms'),fmt(latency(go,'p99'),' ms')]);
    row(['Memory¹',fmt(java.peakSampledMemoryBytes/1048576,' MiB'),fmt(go.peakSampledMemoryBytes/1048576,' MiB')]);
    row(['Delivery errors',fmt(java.errors,''),fmt(go.errors,'')]);
    row(['Result',java.passed?'PASS':'NOT PASSED',go.passed?'PASS':'NOT PASSED']);
    panel.appendChild(table);
    var scope=document.createElement('small');scope.textContent='10 s measured after 10 s warmup · synthetic fixtures and isolated broker · 2 CPUs per runtime. Fixed-load qualification, not maximum capacity. ¹ Peak sampled memory. Full results included in each ZIP.';panel.appendChild(scope);
  }
  byId('form').addEventListener('submit', function (event) { event.preventDefault(); submit(input.value.trim()); });
  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }
  input.addEventListener('input', resizeInput);
  templateButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      input.value = templatePrompts[button.dataset.template];
      resizeInput();
      input.focus();
    });
  });
  input.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat) submit(input.value.trim());
  });
  byId('reset').addEventListener('click', function () { forgetJob(); session++; if (controller) controller.abort(); controller = null; clearInterval(tick); history = []; previousCore = ''; previousGo=''; confirmationToken = ''; pendingJob=null; clearArtifact(); messages.replaceChildren(); byId('timer').textContent = ''; input.value = ''; input.style.height = 'auto'; input.placeholder = 'What should your MI do?'; ui(false); state('Ready to build', 'Describe your idea in the chat.'); welcome(); input.focus(); });
  async function downloadArtifact(item) {
    if (!item) return;
    try {
      var response = await fetch(item.downloadUrl, {signal:AbortSignal.timeout(60000)});
      if(!response.ok) throw new Error('Download expired or unavailable. Generate again.');
      var bytes = new Uint8Array(await response.arrayBuffer());
      var digest = await crypto.subtle.digest('SHA-256', bytes);
      var hex = Array.from(new Uint8Array(digest)).map(function (x) { return x.toString(16).padStart(2, '0'); }).join('');
      if (hex !== item.sha256) throw new Error('Download verification failed. Please generate again.');
      var url = URL.createObjectURL(new Blob([bytes], { type: item.contentType||'application/zip' })); var a = document.createElement('a');
      a.href = url; a.download = (item.filename || 'mi-v1.zip').replace(/[^a-zA-Z0-9_.-]/g, '-'); a.click(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    } catch (error) { state('Download failed', error.message); }
  }
  byId('download').addEventListener('click',function(){if(project)downloadArtifact(project.java||project);});
  byId('download-go').addEventListener('click',function(){if(project)downloadArtifact(project.go);});
  byId('download-config').addEventListener('click',function(){if(project)downloadArtifact(project.configuration);});
  byId('download-tests').addEventListener('click',function(){if(project)downloadArtifact(project.tests);});
  function welcome() { append('assistant', 'What should your MI do? I’ll check whether it already exists in Solace Integration Hub and whether a custom MI fits. If it does, we’ll confirm the API and build it.'); }
  async function loadEndpoint(signal) {
    var config = await fetch('demo-config.json', { cache: 'no-store', signal: signal });
    if (!config.ok) throw new Error('The factory could not load its connection settings. Please retry.');
    var data = await config.json();
    var parsed = new URL(data.apiBaseUrl);
    if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname))) throw new Error('Invalid service URL');
    return parsed.href.replace(/\/$/, '');
  }
  function resumeValidation() {
    try {
      var saved = JSON.parse(sessionStorage.getItem(jobStorageKey) || 'null');
      if (saved && saved.status === 'validating' && /^[a-f0-9]{32}$/.test(saved.jobId || '') && typeof saved.validationToken === 'string' && saved.validationToken.length < 2000) {
        pendingJob = saved;
        request();
      }
    } catch (error) { forgetJob(); }
  }
  welcome();
  resumeValidation();
})();
