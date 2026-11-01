/* AutoResolve frontend — calm light redesign; backend API contract unchanged.
   Endpoints used (unchanged):
     GET  /api/bugs            GET  /api/metrics         GET  /api/bugs/{id}
     POST /api/bugs            POST /api/bugs/{id}/approve
     POST /api/bugs/{id}/feedback   (body: { feedback })                          */
let selected = null;
let currentBugs = [];
let busy = false;
let refreshing = false;
let lastConnected = null;
let queueHtmlCache = '';
let queueAnimated = false;
let metricsLoaded = false;
const feedbackDrafts = {};
const diffStore = [];

const $ = id => document.getElementById(id);

async function api(path, opts = {}) {
    const response = await fetch('/api' + path, {
        headers: { 'Content-Type': 'application/json' },
        ...opts
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = data.detail;
        throw new Error(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `Request failed (${response.status})`);
    }
    return data;
}

/* ---------- helpers ---------- */
function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

const ICONS = {
    'circle-dashed': '<circle cx="12" cy="12" r="9" stroke-dasharray="3 4"/>',
    loader: '<path d="M12 3v4M12 17v4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M3 12h4M17 12h4M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    merge: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="14" r="2.5"/><path d="M6 8.5v7M18 11.5c0-4-6-3-11-5.2"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    chevron: '<path d="m9 6 6 6-6 6"/>'
};
function icon(name, cls = '') {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"${cls ? ` class="${cls}"` : ''}>${ICONS[name] || ''}</svg>`;
}

const STATUS_META = {
    reported: ['Reported', 'circle-dashed'],
    fixing: ['Fixing', 'loader'],
    awaiting_review: ['Awaiting review', 'eye'],
    failed: ['Failed', 'alert'],
    merged: ['Merged', 'merge'],
    passed: ['Passed', 'check']
};

function displayStatus(value) {
    return escapeHtml(value || 'unknown').replaceAll('_', ' ');
}

function statusHtml(value, label) {
    const state = String(value || 'unknown');
    const cls = escapeHtml(state.replace(/[^a-z_]/gi, ''));
    const meta = STATUS_META[state];
    const text = label ? escapeHtml(label) : meta ? meta[0] : displayStatus(state);
    return `<span class="status-badge status-${cls}">${icon(meta ? meta[1] : 'circle-dashed')}${text}</span>`;
}

function sourceInfo(bug) {
    const raw = String(bug.source ?? '').trim();
    if (!raw) return null;
    const s = raw.toLowerCase();
    if (/sheet/.test(s)) return { key: 'sheets', label: 'Sheets' };
    if (/manual|web|form|ui|user/.test(s)) return { key: 'manual', label: 'Manual' };
    return { key: 'other', label: raw.slice(0, 14) };
}

function sourceHtml(bug) {
    const info = sourceInfo(bug);
    return info ? `<span class="source-badge source-${info.key}" title="Source: ${escapeHtml(bug.source)}">${escapeHtml(info.label)}</span>` : '';
}

function toast(message, type = '') {
    const item = document.createElement('div');
    item.className = `toast ${type}`;
    item.textContent = message;
    $('toast-region').appendChild(item);
    setTimeout(() => {
        item.classList.add('leaving');
        setTimeout(() => item.remove(), 260);
    }, 5000);
}

function connection(connected) {
    const element = $('connection-state');
    element.className = `connection-state ${connected ? 'online' : 'offline'}`;
    element.querySelector('span').textContent = connected ? 'Connected to the AutoResolve backend' : 'Disconnected from the AutoResolve backend';
    if (lastConnected !== null && lastConnected !== connected) {
        toast(connected ? 'Reconnected to AutoResolve.' : 'Network disconnected. Retrying automatically.', connected ? 'success' : 'error');
    }
    lastConnected = connected;
}

function repoLabel(repo) {
    const value = String(repo || 'No repository');
    return value.replace(/^https?:\/\/github\.com\//i, '').replace(/\/$/, '');
}

function displayNumber(value, digits = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function parseTime(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
}

function timeAgo(value) {
    const d = parseTime(value);
    if (!d) return '';
    const sec = Math.round((Date.now() - d.getTime()) / 1000);
    if (sec < 45) return 'just now';
    if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.round(sec / 3600)}h ago`;
    if (sec < 86400 * 30) return `${Math.round(sec / 86400)}d ago`;
    return d.toLocaleDateString();
}

function bugTime(bug) {
    return bug.updated_at || bug.created_at || bug.reported_at || '';
}

function emptyReview(title, text) {
    return `<div class="card review-empty"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p><a class="link-arrow" href="#queue">Go to bugs ›</a></div>`;
}

/* ---------- metrics ---------- */
function countStatus(status) {
    return currentBugs.filter(b => b.status === status).length;
}

function metricsRender(metrics) {
    const total = Number.isFinite(Number(metrics.total)) ? Number(metrics.total) : currentBugs.length;
    const merged = Number.isFinite(Number(metrics.merged)) ? Number(metrics.merged) : countStatus('merged');
    const processing = countStatus('fixing');
    const awaiting = countStatus('awaiting_review');
    // [label, value, class, status filter to apply on click]
    const items = [
        ['Total', total, '', 'all'],
        ['Processing', processing, processing ? 'm-proc has' : 'm-proc', 'fixing'],
        ['In review', awaiting, 'm-review', 'awaiting_review'],
        ['Merged', merged, 'm-merged', 'merged']
    ];
    const animate = !metricsLoaded;
    $('metrics').innerHTML = items.map(([label, value, cls, filter], i) => `
        <button type="button" class="metric ${cls} ${animate ? 'fade-in' : ''}" style="--i:${i}" data-filter="${filter}" aria-label="${escapeHtml(label)}: ${escapeHtml(value)}. Show in queue.">
            <strong class="metric-value">${escapeHtml(value)}</strong>
            <span class="metric-label">${escapeHtml(label)}</span>
        </button>`).join('');
    metricsLoaded = true;
}

/* ---------- intake panel + counters ---------- */
function intakeRender() { /* intake card is static in this layout */ }

function sourceFilterRender() {
    const select = $('source-filter');
    const keys = [...new Map(currentBugs.map(sourceInfo).filter(Boolean).map(s => [s.key, s.label])).entries()];
    select.hidden = keys.length === 0;
    const wanted = ['all', ...keys.map(([k]) => k)].join('|');
    if (select.dataset.keys === wanted) return;
    const prev = select.value;
    select.dataset.keys = wanted;
    select.innerHTML = `<option value="all">All sources</option>` + keys.map(([k, l]) => `<option value="${escapeHtml(k)}">${escapeHtml(l)}</option>`).join('');
    select.value = keys.some(([k]) => k === prev) ? prev : 'all';
}

/* ---------- queue ---------- */
function queueRender() {
    const search = ($('bug-search').value || '').trim().toLowerCase();
    const filter = $('status-filter').value;
    const sourceFilter = $('source-filter').hidden ? 'all' : $('source-filter').value;
    const visible = currentBugs.filter(bug => {
        const matchesText = [bug.id, bug.title, bug.repo, bug.repository, bug.description].some(v => String(v || '').toLowerCase().includes(search));
        const matchesSource = sourceFilter === 'all' || sourceInfo(bug)?.key === sourceFilter;
        return matchesText && matchesSource && (filter === 'all' || bug.status === filter);
    });
    $('queue-count').textContent = String(currentBugs.length);
    $('sidebar-count').textContent = String(currentBugs.length);
    $('queue-footer-count').textContent = `${visible.length} of ${currentBugs.length} bugs`;

    const animate = !queueAnimated && visible.length > 0;
    const html = visible.map((bug, i) => {
        const isActive = selected && String(selected.id) === String(bug.id);
        const when = timeAgo(bugTime(bug));
        const meta = [`<span class="mono">${escapeHtml(bug.id)}</span>`, escapeHtml(repoLabel(bug.repo || bug.repository))];
        if (bug.reporter) meta.push(escapeHtml(bug.reporter));
        if (when) meta.push(escapeHtml(when));
        return `
        <button type="button" class="bug-row ${isActive ? 'active' : ''} ${animate ? 'fade-in' : ''}" style="--i:${Math.min(i, 12)}"
            data-bug-id="${escapeHtml(bug.id)}" aria-label="Open ${escapeHtml(bug.id)}: ${escapeHtml(bug.title)}" ${isActive ? 'aria-current="true"' : ''}>
            <span class="bug-text">
                <span class="bug-title">${escapeHtml(bug.title || 'Untitled bug')}</span>
                <span class="bug-meta">${meta.join(' · ')}</span>
            </span>
            <span class="bug-right">${sourceHtml(bug)}${statusHtml(bug.status)}${icon('chevron', 'chevron')}</span>
        </button>`;
    }).join('') || `<div class="empty-state">${currentBugs.length ? 'No bugs match your search or filter.' : 'No bugs yet. New rows in your Google Sheet will appear here once imported.'}</div>`;

    if (html !== queueHtmlCache) {
        const list = $('bugs');
        const top = list.scrollTop;
        list.innerHTML = html;
        list.scrollTop = top;
        queueHtmlCache = html;
    }
    if (visible.length) queueAnimated = true;
}

async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
        const [bugs, metrics] = await Promise.all([api('/bugs'), api('/metrics')]);
        currentBugs = Array.isArray(bugs) ? bugs : [];
        metricsRender(metrics);
        sourceFilterRender();
        intakeRender();
        connection(true);
        if (selected) {
            try {
                const current = await api('/bugs/' + encodeURIComponent(selected.id));
                const changed = JSON.stringify(current) !== JSON.stringify(selected);
                selected = current;
                if (changed) render();
            } catch (error) {
                selected = null;
                $('detail').innerHTML = emptyReview('Bug not found', 'It may have been removed. Choose another bug from the list.');
            }
        }
        queueRender();
    } catch (error) {
        connection(false);
        queueHtmlCache = '';
        $('bugs').innerHTML = `<div class="empty-state">Can’t load bugs. Check that your AutoResolve server is running.</div>`;
        $('metrics').innerHTML = `<div class="metric err"><span class="metric-label">Can’t load metrics.</span></div>`;
    } finally {
        refreshing = false;
    }
}

/* ---------- manual report ---------- */
function setFieldError(inputId, message) {
    const input = $(inputId);
    const err = $(inputId + '-err');
    if (err) err.textContent = message || '';
    input.closest('.field')?.classList.toggle('invalid', !!message);
    input.setAttribute('aria-invalid', message ? 'true' : 'false');
}

async function createBug() {
    if (busy) return;
    const title = $('title').value.trim();
    const description = $('description').value.trim();
    const repository = $('repo').value.trim();
    const reporter = $('reporter').value.trim();
    setFieldError('title', title ? '' : 'Enter a short title.');
    setFieldError('description', description ? '' : 'Describe what went wrong.');
    setFieldError('repo', repository ? '' : 'Enter the GitHub repository.');
    if (!title || !description || !repository) {
        toast('Enter a title, description, and repository.', 'error');
        return;
    }
    busy = true;
    const button = $('create-button');
    button.disabled = true;
    button.textContent = 'Submitting…';
    try {
        const bug = await api('/bugs', {
            method: 'POST',
            body: JSON.stringify({ title, description, repository, reporter })
        });
        $('title').value = '';
        $('description').value = '';
        toast('Report submitted.', 'success');
        await refresh();
        await showBug(bug.id);
    } catch (error) {
        toast('Couldn’t submit report: ' + error.message, 'error');
    } finally {
        busy = false;
        button.disabled = false;
        button.textContent = 'Submit report';
    }
}

/* ---------- details ---------- */
async function showBug(id) {
    try {
        selected = await api('/bugs/' + encodeURIComponent(id));
        queueRender();
        render();
        $('review').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
        toast('Couldn’t open bug: ' + error.message, 'error');
    }
}

function renderDiff(diff) {
    const lines = String(diff || '').split('\n');
    if (lines.length && lines[lines.length - 1] === '') lines.pop();
    let oldNo = 0, newNo = 0;
    return lines.map(line => {
        let cls = '', a = '', b = '';
        const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(line);
        if (hunk) { oldNo = Number(hunk[1]); newNo = Number(hunk[2]); cls = 'hunk'; }
        else if (/^(\+\+\+|---|diff |index )/.test(line)) { cls = 'meta'; }
        else if (line.startsWith('+')) { cls = 'add'; b = newNo++; }
        else if (line.startsWith('-')) { cls = 'del'; a = oldNo++; }
        else if (oldNo || newNo) { a = oldNo++; b = newNo++; }
        return `<div class="dl ${cls}"><span class="ln">${a}</span><span class="ln">${b}</span><span class="lc">${escapeHtml(line)}</span></div>`;
    }).join('');
}

function diffStats(diff) {
    let add = 0, del = 0;
    String(diff || '').split('\n').forEach(l => {
        if (l.startsWith('+') && !l.startsWith('+++')) add++;
        else if (l.startsWith('-') && !l.startsWith('---')) del++;
    });
    return { add, del };
}
function getValidationStatus(results = {}) {
    if (results.passed === true) {
        return 'passed';
    }

    if (
        results.stage === 'baseline_blocked' &&
        results.focused_regression_passed === true
    ) {
        return 'partial';
    }

    if (results.passed === false) {
        return 'failed';
    }

    return 'pending';
}

/* Pipeline stages: only mark what the backend data confirms. */
function pipelineStages(bug) {
    const attempts = Array.isArray(bug.attempts) ? bug.attempts : [];
    const files = Array.isArray(bug.changed_files) ? bug.changed_files : [];
    const history = Array.isArray(bug.history) ? bug.history : [];
    const tr = bug.test_results || {};
    const status = bug.status;
    const merged = status === 'merged';
    const failedRun = status === 'failed';
    const hasTests = typeof tr.passed === 'boolean';
    const validationStatus = getValidationStatus(tr);
    const prConfirmed = !!(bug.pr_url || bug.pull_request_url || bug.pr_number) ||
        history.some(h => /pull request|\bpr\b.{0,12}(creat|open)/i.test(`${h.event || ''} ${h.message || ''}`));

    const defs = [
        { name: 'Imported', done: true },
        { name: 'Analyzing', done: !!bug.root_cause || merged, active: status === 'fixing' && !bug.root_cause },
        { name: 'Fix generated', done: files.length > 0 || merged, active: status === 'fixing' && !!bug.root_cause && !files.length },
        {
            name: 'Validating',
            done: validationStatus === 'passed',
            partial: validationStatus === 'partial',
            bad: validationStatus === 'failed',
            active: validationStatus === 'pending' &&
                status === 'fixing' && files.length > 0
        },
        { name: 'PR created', done: prConfirmed || merged },
        { name: 'Developer review', done: merged, active: status === 'awaiting_review', needsYou: true },
        { name: 'Merged', done: merged }
    ];
    let failMarked = defs.some(d => d.bad);
    return defs.map(d => {
        let state = 'pending', text = 'Not confirmed';
        if (d.bad) {
            state = 'failed';
            text = 'Tests failed';
        } else if (d.partial) {
            state = 'partial';
            text = 'Partially validated';
        } else if (d.done) {
            state = 'done';
            text = 'Confirmed';
        }
        else if (d.done) { state = 'done'; text = 'Confirmed'; }
        else if (d.active) { state = 'current'; text = d.needsYou ? 'Needs your decision' : 'In progress'; }
        else if (failedRun && !failMarked) { state = 'failed'; text = 'Run failed'; failMarked = true; }
        return { name: d.name, state, text, needsYou: !!(d.needsYou && state === 'current') };
    });
}

function pipelineHtml(bug) {
    const stages = pipelineStages(bug);
    const glyph = s =>
        s === 'done' ? icon('check') :
        s === 'failed' ? icon('x') :
        s === 'partial' ? icon('alert') :
        s === 'current' ? icon('loader') : '';
    return `<div class="card pipeline">
        <h4>Repair pipeline</h4>
        <p>Stages appear as confirmed only when the backend data shows them.</p>
        <ol class="stepper">${stages.map(s => `
            <li class="step ${s.state} ${s.needsYou ? 'needs-you' : ''}" ${s.state === 'current' ? 'aria-current="step"' : ''}>
                <span class="step-dot">${glyph(s.state)}</span>
                <span class="step-text"><span class="step-name">${escapeHtml(s.name)}</span><span class="step-state">${escapeHtml(s.text)}</span></span>
            </li>`).join('')}</ol></div>`;
}

function render() {
    if (!selected) return;
    const bug = selected;
    const attempts = Array.isArray(bug.attempts) ? bug.attempts : [];
    const latest = attempts.length ? attempts[attempts.length - 1] : null;
    const changedFiles = Array.isArray(bug.changed_files) ? bug.changed_files : [];
    const history = Array.isArray(bug.history) ? bug.history : [];
    const feedbackItems = Array.isArray(bug.feedback) ? bug.feedback : [];
    const testResults = bug.test_results || {};
    const plan = latest?.plan;
    const planItems = Array.isArray(plan) ? plan : plan ? [plan] : [];

    // Keep <details> open/closed state and textarea focus across auto-refresh re-renders.
    const openFolds = new Set([...document.querySelectorAll('#detail details[data-fold][open]')].map(d => d.dataset.fold));
    const hadFocus = document.activeElement && document.activeElement.id === 'feedback-text';
    const selStart = hadFocus ? document.activeElement.selectionStart : 0;
    const isOpen = (key, dflt) => (document.querySelector('#detail details[data-fold]') ? openFolds.has(key) : dflt);
    diffStore.length = 0;

    const filesHtml = changedFiles.length ? changedFiles.map(file => {
        const idx = diffStore.push(String(file.diff || '')) - 1;
        const st = diffStats(file.diff);
        return `<div class="file-block">
            <div class="file-header">
                <span class="file-path" title="${escapeHtml(file.path || '')}">${escapeHtml(file.path || 'Unknown file')}</span>
                ${file.diff ? `<span class="file-stats"><span class="add">+${st.add}</span><span class="del">−${st.del}</span></span>
                <button type="button" class="copy-btn" data-copy="${idx}" aria-label="Copy diff for ${escapeHtml(file.path || 'file')}">Copy</button>` : ''}
            </div>
            ${file.diff ? `<div class="diff" tabindex="0" role="region" aria-label="Diff for ${escapeHtml(file.path || 'file')}">${renderDiff(file.diff)}</div>` : '<p class="empty-copy" style="padding:14px 16px">No diff recorded.</p>'}
        </div>`;
    }).join('') : '<p class="empty-copy">No changed files yet.</p>';

    const draft = feedbackDrafts[bug.id] || '';
    const decisionHtml = bug.status === 'awaiting_review' ? `
        <div class="card decision">
            <div>
                <h4>Ready for your review</h4>
                <p>Approving asks the backend to merge the pull request into the target repository, if merging is enabled.</p>
            </div>
            <div class="decision-actions">
                <button class="button button-primary" id="approve-button" type="button">Approve &amp; Merge</button>
            </div>
            <div class="feedback-box">
                <label for="feedback-text">Not quite right? Request changes</label>
                <textarea id="feedback-text" rows="3" placeholder="What should change in this fix?">${escapeHtml(draft)}</textarea>
                <button class="button button-secondary" id="feedback-button" type="button">Send feedback</button>
            </div>
        </div>`
        : bug.status === 'fixing' ? '<div class="notice">AI repair in progress. This page updates automatically.</div>'
        : bug.status === 'failed' ? '<div class="notice fail">Repair failed. Check the latest attempt, test results, and history below.</div>'
        : bug.status === 'merged' ? '<div class="notice success">This fix has been merged.</div>' : '';

    const validationStatus = getValidationStatus(testResults);

    const testsPassed = validationStatus === 'passed';
    const testsFailed = validationStatus === 'failed';

    const resultBadge =
        validationStatus === 'passed'
            ? statusHtml('passed', 'Passed')
            : validationStatus === 'partial'
                ? statusHtml('reported', 'Partially validated')
                : validationStatus === 'failed'
                    ? statusHtml('failed', 'Failed')
                    : statusHtml('reported', 'Recorded');
    const hasResults = Object.keys(testResults).length > 0;

    const fold = (key, title, right, body, dflt) =>
        `<details class="card fold" data-fold="${key}" ${isOpen(key, dflt) ? 'open' : ''}><summary>${title}<span class="sum-right">${right}</span></summary><div class="fold-body">${body}</div></details>`;

    $('detail').innerHTML = `<div class="review">
        <div class="card r-card">
            <div class="r-top">
                <div>
                    <span class="r-id">${escapeHtml(bug.id)}</span>
                    <h3>${escapeHtml(bug.title || 'Untitled bug')}</h3>
                    <p class="r-desc">${escapeHtml(bug.description || 'No description')}</p>
                </div>
                <div class="r-badges">${sourceHtml(bug)}${statusHtml(bug.status)}</div>
            </div>
            <div class="r-meta">
                <div><span>Repository</span><strong class="mono">${escapeHtml(repoLabel(bug.repo || bug.repository))}</strong></div>
                <div><span>Reported by</span><strong>${escapeHtml(bug.reporter || 'Unknown')}</strong></div>
                <div><span>Attempt</span><strong>${escapeHtml(bug.iteration ?? 0)} of ${escapeHtml(bug.max_iterations ?? 3)}</strong></div>
                <div><span>Branch</span><strong class="mono">${escapeHtml(bug.branch || 'Not created')}</strong></div>
            </div>
        </div>
        ${decisionHtml}
        ${pipelineHtml(bug)}
        <div class="card block"><h4>Root cause</h4><p>${escapeHtml(bug.root_cause || 'Not analyzed yet.')}</p></div>
        <div class="card block"><h4>Proposed fix</h4>
            ${latest ? `<div class="attempt-box"><span>Attempt ${escapeHtml(latest.iteration ?? '?')} · ${escapeHtml(latest.outcome || 'Unknown outcome')}</span><strong>${escapeHtml(latest.summary || 'No summary')}</strong></div>
            <p class="sub-label">Plan</p>${planItems.length ? `<ol class="repair-plan">${planItems.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ol>` : '<p class="empty-copy">No plan recorded.</p>'}` : '<p class="empty-copy">No attempts yet.</p>'}
        </div>
        <div class="card block"><h4>Changed files</h4>${filesHtml}</div>
        ${fold('tests', 'Test results', resultBadge,
            hasResults ? `<pre class="test-out ${testsPassed ? 'pass' : testsFailed ? 'fail' : ''}">${escapeHtml(JSON.stringify(testResults, null, 2))}</pre>` : '<p class="empty-copy">No test results recorded.</p>', true)}
        ${fold('feedback', 'Feedback', feedbackItems.length ? `<span class="count-pill" style="font-size:13px">${feedbackItems.length}</span>` : '',
            feedbackItems.length ? feedbackItems.map(item => `<div class="feedback-item"><time>${escapeHtml(item.at || '')}</time>${escapeHtml(item.text || '')}</div>`).join('') : '<p class="empty-copy">No feedback yet.</p>', false)}
        ${fold('history', 'History', history.length ? `<span class="count-pill" style="font-size:13px">${history.length}</span>` : '',
            history.length ? `<div class="timeline">${history.map(item => `<div class="timeline-item"><strong>${escapeHtml(displayStatus(item.event))}</strong><time>${escapeHtml(item.at || '')}</time><p>${escapeHtml(item.message || '')}</p></div>`).join('')}</div>` : '<p class="empty-copy">No activity yet.</p>', false)}
    </div>`;

    const ta = $('feedback-text');
    if (ta && hadFocus) { ta.focus({ preventScroll: true }); try { ta.setSelectionRange(selStart, selStart); } catch (e) { /* ignore */ } }
}

/* ---------- actions ---------- */
async function action(path) {
    if (!selected || busy) return;
    busy = true;
    const id = selected.id;
    const btn = $('approve-button');
    if (btn) { btn.disabled = true; btn.textContent = 'Merging…'; }
    try {
        selected = await api('/bugs/' + encodeURIComponent(id) + path, { method: 'POST' });
        render();
        await refresh();
        toast(path === '/approve' ? `Approval accepted by the backend. Status: ${String(selected?.status || 'updated').replaceAll('_', ' ')}.` : 'Done.', 'success');
    } catch (error) {
        toast('Action failed: ' + error.message, 'error');
        if (selected && String(selected.id) === String(id)) render();
    } finally { busy = false; }
}

function confirmApprove() {
    const dialog = $('confirm-dialog');
    $('confirm-bug').textContent = `${selected.id} · ${selected.title || 'Untitled bug'}`;
    if (typeof dialog.showModal !== 'function') {
        return Promise.resolve(window.confirm('Approve and merge this fix? This will merge the GitHub pull request into the target repository.'));
    }
    return new Promise(resolve => {
        const done = () => { dialog.removeEventListener('close', done); resolve(dialog.returnValue === 'confirm'); };
        dialog.returnValue = 'cancel';
        dialog.addEventListener('close', done);
        dialog.showModal();
    });
}

async function approve() {
    if (!selected || busy) return;
    if (!(await confirmApprove())) return;
    await action('/approve');
}

async function feedback() {
    if (!selected || busy) return;
    const box = $('feedback-text');
    const text = (box?.value || '').trim();
    if (!text) { toast('Write what should change first.', 'error'); box?.focus(); return; }
    busy = true;
    const btn = $('feedback-button');
    if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
    try {
        const id = selected.id;
        selected = await api('/bugs/' + encodeURIComponent(id) + '/feedback', {
            method: 'POST', body: JSON.stringify({ feedback: text })
        });
        delete feedbackDrafts[id];
        render();
        await refresh();
        toast('Feedback sent.', 'success');
    } catch (error) {
        toast('Couldn’t send feedback: ' + error.message, 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Send feedback'; }
    } finally { busy = false; }
}

async function copyDiff(idx) {
    const text = diffStore[idx];
    if (typeof text !== 'string') return;
    try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
        else {
            const t = document.createElement('textarea');
            t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
            document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove();
        }
        toast('Diff copied.', 'success');
    } catch (e) {
        toast('Couldn’t copy the diff.', 'error');
    }
}

/* ---------- init ---------- */
function init() {
    $('report-form').addEventListener('submit', event => { event.preventDefault(); createBug(); });
    ['title', 'description', 'repo'].forEach(id => $(id).addEventListener('input', () => setFieldError(id, '')));

    $('bugs').addEventListener('click', event => {
        const row = event.target.closest('[data-bug-id]');
        if (row) showBug(row.dataset.bugId);
    });

    // Metric cards double as shortcuts to the filtered queue.
    $('metrics').addEventListener('click', event => {
        const card = event.target.closest('[data-filter]');
        if (!card) return;
        $('status-filter').value = card.dataset.filter;
        queueRender();
        $('queue').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // Delegated handlers for the review area (render() replaces its markup).
    $('detail').addEventListener('click', event => {
        if (event.target.closest('#approve-button')) approve();
        else if (event.target.closest('#feedback-button')) feedback();
        else {
            const copy = event.target.closest('[data-copy]');
            if (copy) copyDiff(Number(copy.dataset.copy));
        }
    });
    $('detail').addEventListener('input', event => {
        if (event.target.id === 'feedback-text' && selected) feedbackDrafts[selected.id] = event.target.value;
    });

    $('bug-search').addEventListener('input', queueRender);
    $('status-filter').addEventListener('change', queueRender);
    $('source-filter').addEventListener('change', queueRender);
    $('queue-refresh-button').addEventListener('click', refresh);
    $('new-report-button').addEventListener('click', () => {
        $('report').scrollIntoView({ behavior: 'smooth', block: 'start' });
        $('title').focus({ preventScroll: true });
    });

    const links = $('nav-links');
    const navLinks = document.querySelectorAll('.nav-link');
    $('menu-toggle').addEventListener('click', () => {
        const open = links.classList.toggle('open');
        $('menu-toggle').setAttribute('aria-expanded', String(open));
    });
    navLinks.forEach(link => link.addEventListener('click', () => {
        links.classList.remove('open');
        $('menu-toggle').setAttribute('aria-expanded', 'false');
    }));

    // Highlight the nav link for the section in view.
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                navLinks.forEach(l => l.classList.toggle('active', l.dataset.section === entry.target.id));
            });
        }, { rootMargin: '-40% 0px -55% 0px' });
        ['overview', 'queue', 'review', 'report'].forEach(id => observer.observe($(id)));
    }

    refresh();
    setInterval(() => { if (!document.hidden) refresh(); }, 5000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
}

init();