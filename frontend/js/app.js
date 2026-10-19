let selected = null;

async function api(path, opts = {}) {
    const response = await fetch("/api" + path, {
        headers: { "Content-Type": "application/json" },
        ...opts
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || `Request failed (${response.status})`);
    }

    return data;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function displayStatus(status) {
    return escapeHtml(status || "unknown").replaceAll("_", " ");
}

async function createBug() {
    try {
        const bug = await api("/bugs", {
            method: "POST",
            body: JSON.stringify({
                title: document.getElementById("title").value,
                description: document.getElementById("description").value,
                repository: document.getElementById("repo").value,
                reporter: document.getElementById("reporter").value
            })
        });

        document.getElementById("title").value = "";
        document.getElementById("description").value = "";

        await refresh();
        await showBug(bug.id);
    } catch (error) {
        alert("Could not create bug: " + error.message);
    }
}

async function refresh() {
    try {
        const [bugs, metrics] = await Promise.all([
            api("/bugs"),
            api("/metrics")
        ]);

        document.getElementById("bugs").innerHTML = bugs.map(bug => `
            <div class="bug" data-bug-id="${escapeHtml(bug.id)}" role="button" tabindex="0">
                <b>${escapeHtml(bug.id)} — ${escapeHtml(bug.title)}</b><br>
                <span class="badge">${displayStatus(bug.status)}</span>
                · Iteration ${bug.iteration} / ${bug.max_iterations}
            </div>
        `).join("") || "No bugs reported yet.";

        document.querySelectorAll("[data-bug-id]").forEach(element => {
            const openBug = () => showBug(element.dataset.bugId);
            element.addEventListener("click", openBug);
            element.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openBug();
                }
            });
        });

        document.getElementById("metrics").innerHTML = `
            <div class="metric"><b>Total Bugs</b><br>${metrics.total}</div>
            <div class="metric"><b>Resolved</b><br>${metrics.merged}/${metrics.total}</div>
            <div class="metric"><b>First Try</b><br>${(metrics.first_attempt_rate * 100).toFixed(0)}%</div>
            <div class="metric"><b>Avg. Iterations</b><br>${metrics.avg_iterations.toFixed(1)}</div>
            <div class="metric"><b>Change Requests</b><br>${metrics.change_requests}</div>
        `;
    } catch (error) {
        document.getElementById("bugs").textContent =
            "Could not load bugs: " + error.message;
        document.getElementById("metrics").textContent =
            "Could not load metrics.";
    }
}

async function showBug(id) {
    try {
        selected = await api("/bugs/" + encodeURIComponent(id));
        render();
    } catch (error) {
        alert("Could not load bug: " + error.message);
    }
}

function render() {
    const bug = selected;
    if (!bug) return;

    const attempts = bug.attempts || [];
    const latest = attempts.length ? attempts[attempts.length - 1] : null;
    const changedFiles = bug.changed_files || [];
    const history = bug.history || [];
    const feedback = bug.feedback || [];
    const testResults = bug.test_results || {};

    const plan = latest?.plan;
    const planHtml = Array.isArray(plan)
        ? plan.map(item => `<li>${escapeHtml(item)}</li>`).join("")
        : plan ? `<li>${escapeHtml(plan)}</li>` : "";

    const filesHtml = changedFiles.length
        ? changedFiles.map(file => `
            <li>
                <b>${escapeHtml(file.path || "Unknown file")}</b>
                ${file.diff ? `<pre class="diff">${escapeHtml(file.diff)}</pre>` : ""}
            </li>
        `).join("")
        : "<li>None recorded</li>";

    const actionsHtml = bug.status === "awaiting_review" ? `
        <button id="approve-button">Approve &amp; Merge</button>
        <button id="feedback-button">Request Changes</button>
    ` : bug.status === "fixing"
        ? "<p>Repair is in progress. Refreshing automatically.</p>"
        : bug.status === "failed"
            ? "<p>The repair failed. Review the history and validation results.</p>"
            : bug.status === "merged"
                ? "<p>This repair has been merged.</p>"
                : "";

    document.getElementById("detail").innerHTML = `
        <h3>${escapeHtml(bug.id)} — ${escapeHtml(bug.title)}</h3>
        <p>${escapeHtml(bug.description)}</p>
        <p><b>Repository:</b> ${escapeHtml(bug.repo)}</p>
        <p><b>Reporter:</b> ${escapeHtml(bug.reporter)}</p>
        <p><b>Status:</b> <span class="badge">${displayStatus(bug.status)}</span></p>
        <p><b>Iteration:</b> ${bug.iteration} / ${bug.max_iterations}</p>
        <p><b>Root cause:</b> ${escapeHtml(bug.root_cause || "Not analyzed yet")}</p>
        <p><b>Branch:</b> ${escapeHtml(bug.branch || "Not created")}</p>

        <h4>Changed Files</h4>
        <ul>${filesHtml}</ul>

        ${latest ? `
            <h4>Latest Attempt — ${latest.iteration}</h4>
            <p><b>Summary:</b> ${escapeHtml(latest.summary || "No summary")}</p>
            <p><b>Outcome:</b> ${escapeHtml(latest.outcome || "Unknown")}</p>
            <h4>Plan</h4>
            <ul>${planHtml || "<li>No plan recorded</li>"}</ul>
            <h4>Validation Results</h4>
            <pre class="diff ${testResults.passed === true ? "pass" : "fail"}">${escapeHtml(JSON.stringify(testResults, null, 2))}</pre>
        ` : "<p>No repair attempt has been recorded yet.</p>"}

        ${actionsHtml}

        <h4>Feedback</h4>
        ${feedback.length
            ? `<ul>${feedback.map(item => `<li>${escapeHtml(item.at || "")}: ${escapeHtml(item.text || "")}</li>`).join("")}</ul>`
            : "<p>No feedback recorded.</p>"}

        <h4>History</h4>
        ${history.length
            ? history.map(item => `
                <div>• ${escapeHtml(item.at || "")} —
                    <b>${escapeHtml(item.event || "")}</b>
                    ${escapeHtml(item.message || "")}
                </div>
            `).join("")
            : "<p>No history recorded.</p>"}
    `;

    document.getElementById("approve-button")?.addEventListener("click", approve);
    document.getElementById("feedback-button")?.addEventListener("click", feedback);
}

async function action(path) {
    if (!selected) return;

    try {
        const id = selected.id;
        selected = await api("/bugs/" + encodeURIComponent(id) + path, {
            method: "POST"
        });
        render();
        await refresh();
    } catch (error) {
        alert("Action failed: " + error.message);
    }
}

async function approve() {
    await action("/approve");
}

async function feedback() {
    if (!selected) return;

    const text = prompt("Describe the changes you want:");
    if (!text || !text.trim()) return;

    try {
        const id = selected.id;
        selected = await api("/bugs/" + encodeURIComponent(id) + "/feedback", {
            method: "POST",
            body: JSON.stringify({ feedback: text.trim() })
        });
        render();
        await refresh();
    } catch (error) {
        alert("Could not submit feedback: " + error.message);
    }
}

refresh();
setInterval(refresh, 5000);
