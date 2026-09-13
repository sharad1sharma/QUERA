const TYPE_ICONS = { url: "🔗", image: "🖼️", video: "🎬", file: "📄" };
let charts = {};

function showAdminError(message) {
    let banner = document.getElementById("adminError");
    if (!banner) {
        banner = document.createElement("p");
        banner.id = "adminError";
        banner.style.color = "#d32f2f";
        banner.style.fontWeight = "600";
        banner.style.margin = "0 0 12px";
        document.querySelector("main.container").prepend(banner);
    }
    banner.textContent = message;
}

async function init() {
    const user = await requireAdmin();
    if (!user) return;
    await renderAuthNav("navAuthSlot");

    // Each section loads independently, tagged by name, so one failing
    // request (e.g. an API that's unreachable) shows exactly which section
    // broke and why instead of leaving every table/chart silently blank.
    const sections = [
        ["stats", loadStats],
        ["charts", loadCharts],
        ["users", loadUsers],
        ["resources", loadResources],
        ["ai insights", loadAiInsights],
    ];

    const results = await Promise.allSettled(sections.map(([, fn]) => fn()));

    const failed = results
        .map((r, i) => ({ name: sections[i][0], result: r }))
        .filter(({ result }) => result.status === "rejected");

    if (failed.length > 0) {
        failed.forEach(({ name, result }) => console.error(`Admin dashboard: ${name} failed to load:`, result.reason));
        const details = failed.map(({ name, result }) => `${name} (${result.reason?.message || result.reason})`).join(", ");
        showAdminError(
            `Could not load: ${details}. Check that the backend is reachable and that CORS_ORIGINS in .env matches how you're opening this page, then click Refresh.`
        );
    }
}

async function loadStats() {
    const response = await fetch(`${API}/admin/stats`, { credentials: "include" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
    const s = result.data;

    document.getElementById("statUsers").textContent = s.total_users;
    document.getElementById("statResources").textContent = s.total_resources;
    document.getElementById("statUrls").textContent = s.total_urls;
    document.getElementById("statImages").textContent = s.total_images;
    document.getElementById("statVideos").textContent = s.total_videos;
    document.getElementById("statFiles").textContent = s.total_files;
    document.getElementById("statPublic").textContent = s.public_resources;
    document.getElementById("statPrivate").textContent = s.private_resources;
    document.getElementById("statQr").textContent = s.total_qr_codes;
    document.getElementById("statClicks").textContent = s.total_clicks;

    return s;
}

function upsertChart(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), config);
}

async function loadCharts() {
    await window.chartJsReady;
    const stats = await loadStats();

    // Resources created over time
    const timelineResp = await fetch(`${API}/admin/stats/timeline?days=14`, { credentials: "include" });
    const timelineResult = await timelineResp.json();
    if (!timelineResp.ok) throw new Error(timelineResult.error || `Request failed (${timelineResp.status})`);
    const timeline = timelineResult.data;
    upsertChart("timelineChart", {
        type: "line",
        data: {
            labels: timeline.map(t => t.day),
            datasets: [{ label: "Resources created", data: timeline.map(t => t.count), borderColor: "#4b55e8", backgroundColor: "rgba(75,85,232,0.15)", fill: true, tension: 0.3 }]
        },
        options: { responsive: true, plugins: { title: { display: true, text: "Resources created (last 14 days)" } } }
    });

    // Resources by type
    upsertChart("typeChart", {
        type: "bar",
        data: {
            labels: ["URL", "Image", "Video", "File"],
            datasets: [{ label: "Count", data: [stats.total_urls, stats.total_images, stats.total_videos, stats.total_files], backgroundColor: ["#4b55e8", "#18a957", "#e5983b", "#6841d8"] }]
        },
        options: { responsive: true, plugins: { title: { display: true, text: "Resources by type" }, legend: { display: false } } }
    });

    // Public vs private
    upsertChart("visibilityChart", {
        type: "doughnut",
        data: {
            labels: ["Public", "Private"],
            datasets: [{ data: [stats.public_resources, stats.private_resources], backgroundColor: ["#18a957", "#e53935"] }]
        },
        options: { responsive: true, plugins: { title: { display: true, text: "Public vs Private" } } }
    });

    // Per-user resource counts
    const byUserResp = await fetch(`${API}/admin/stats/by-user`, { credentials: "include" });
    const byUserResult = await byUserResp.json();
    if (!byUserResp.ok) throw new Error(byUserResult.error || `Request failed (${byUserResp.status})`);
    const byUser = byUserResult.data;
    upsertChart("userChart", {
        type: "bar",
        data: {
            labels: byUser.map(u => u.username),
            datasets: [{ label: "Resources", data: byUser.map(u => u.count), backgroundColor: "#2164d9" }]
        },
        options: { responsive: true, indexAxis: "y", plugins: { title: { display: true, text: "Resources per user" }, legend: { display: false } } }
    });

    // AI risk distribution (URLs only, from real analyzed data)
    const riskResp = await fetch(`${API}/ai/admin/risk-distribution`, { credentials: "include" });
    const riskResult = await riskResp.json();
    if (!riskResp.ok) throw new Error(riskResult.error || `Request failed (${riskResp.status})`);
    const riskColors = { low: "#18a957", medium: "#e5983b", high: "#e53935", unrated: "#9e9e9e" };
    const risk = riskResult.data;
    upsertChart("riskChart", {
        type: "doughnut",
        data: {
            labels: risk.map(r => r.level),
            datasets: [{ data: risk.map(r => r.count), backgroundColor: risk.map(r => riskColors[r.level] || "#9e9e9e") }]
        },
        options: { responsive: true, plugins: { title: { display: true, text: "AI risk distribution (URLs)" } } }
    });
}

async function loadAiInsights() {
    const list = document.getElementById("aiInsightsList");
    try {
        const response = await fetch(`${API}/ai/admin/insights`, { credentials: "include" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
        const insights = result.data.insights;
        list.innerHTML = insights.length
            ? insights.map(text => `<li>${escapeHtml(text)}</li>`).join("")
            : "<li>Not enough data yet for insights.</li>";
    } catch (error) {
        list.innerHTML = `<li>Could not load AI insights.</li>`;
        throw error;
    }
}

async function loadUsers() {
    const response = await fetch(`${API}/admin/users`, { credentials: "include" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
    const body = document.getElementById("userBody");
    body.innerHTML = "";

    result.data.forEach((user, index) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${index + 1}</td>
            <td>${escapeHtml(user.username)}</td>
            <td>${escapeHtml(user.email)}</td>
            <td>
                <select class="role-select" data-id="${user.id}">
                    <option value="user" ${user.role === "user" ? "selected" : ""}>User</option>
                    <option value="admin" ${user.role === "admin" ? "selected" : ""}>Admin</option>
                </select>
            </td>
            <td>${formatDate(user.created_at)}</td>
            <td><button class="delete" data-delete-user="${user.id}">Delete</button></td>
        `;
        body.appendChild(tr);
    });

    if (result.data.length === 0) {
        body.innerHTML = `<tr><td colspan="6">No users found.</td></tr>`;
    }
}

document.addEventListener("change", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.classList.contains("role-select")) {
        const id = target.dataset.id;
        const role = target.value;
        await fetch(`${API}/admin/users/${id}/role`, {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role })
        });
    } else if (target.classList.contains("admin-visibility-select")) {
        const id = target.dataset.id;
        const visibility = target.value;
        await fetch(`${API}/admin/resources/${id}`, {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ visibility })
        });
        await loadStats();
    }
});

document.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.dataset.deleteUser) {
        if (!confirm("Delete this user? Their resources will remain but become unowned.")) return;
        const response = await fetch(`${API}/admin/users/${target.dataset.deleteUser}`, { method: "DELETE", credentials: "include" });
        const result = await response.json();
        if (!response.ok) { alert(result.error); return; }
        await loadUsers();
        await loadStats();
    } else if (target.dataset.deleteResource) {
        if (!confirm("Delete this resource?")) return;
        const response = await fetch(`${API}/admin/resources/${target.dataset.deleteResource}`, { method: "DELETE", credentials: "include" });
        const result = await response.json();
        if (!response.ok) { alert(result.error); return; }
        await loadResources();
        await loadStats();
    } else if (target.dataset.editResource) {
        const id = target.dataset.editResource;
        const newUrl = prompt("Edit destination URL:");
        if (!newUrl) return;
        await fetch(`${API}/admin/resources/${id}`, {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: newUrl.trim() })
        });
        await loadResources();
    }
});

async function loadResources() {
    const search = encodeURIComponent(document.getElementById("searchInput").value.trim());
    const response = await fetch(`${API}/admin/resources?search=${search}`, { credentials: "include" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
    const body = document.getElementById("resourceBody");
    body.innerHTML = "";

    result.data.forEach((item, index) => {
        const tr = document.createElement("tr");
        const label = item.resource_type === "url"
            ? escapeHtml(item.original_url || "")
            : escapeHtml(item.original_name || "unnamed");

        tr.innerHTML = `
            <td>${index + 1}</td>
            <td>${escapeHtml(item.owner_username || "unowned")}</td>
            <td>${TYPE_ICONS[item.resource_type] || ""} ${item.resource_type}</td>
            <td title="${label}">${label.length > 35 ? label.slice(0, 35) + "..." : label}</td>
            <td><a href="${item.short_url}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.short_code)}</a></td>
            <td>
                <select class="admin-visibility-select" data-id="${item.id}">
                    <option value="public" ${item.visibility === "public" ? "selected" : ""}>🌐 Public</option>
                    <option value="private" ${item.visibility === "private" ? "selected" : ""}>🔒 Private</option>
                </select>
            </td>
            <td>${item.click_count}</td>
            <td>${formatDate(item.created_at)}</td>
            <td>
                <div class="actions">
                    ${item.resource_type === "url" ? `<button class="edit" data-edit-resource="${item.id}">Edit</button>` : ""}
                    <button class="delete" data-delete-resource="${item.id}">Delete</button>
                </div>
            </td>
        `;
        body.appendChild(tr);
    });

    if (result.data.length === 0) {
        body.innerHTML = `<tr><td colspan="9">No resources found.</td></tr>`;
    }
}

document.getElementById("refreshBtn").addEventListener("click", async (event) => {
    setButtonLoading(event.currentTarget, true);
    try {
        await Promise.all([loadResources(), loadStats()]);
    } catch (error) {
        showAdminError("Could not refresh. Check that the backend is running and reachable.");
    } finally {
        setButtonLoading(event.currentTarget, false);
    }
});

let searchTimer;
document.getElementById("searchInput").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadResources, 300);
});

init();
