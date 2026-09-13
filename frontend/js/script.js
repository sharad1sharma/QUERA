// Relies on API, escapeHtml, formatDate, fetchCurrentUser, renderAuthNav
// which are defined in auth-common.js (loaded before this file).

const urlInput = document.getElementById("urlInput");
const shortenBtn = document.getElementById("shortenBtn");
const result = document.getElementById("result");
const shortUrl = document.getElementById("shortUrl");
const message = document.getElementById("message");
const historyBody = document.getElementById("historyBody");
const searchInput = document.getElementById("searchInput");

let currentShortUrl = "";
let loggedInUser = null;

function showMessage(text, error = false) {
    message.textContent = text;
    message.style.color = error ? "#d32f2f" : "#15934a";
}

function isHttpUrl(value) {
    try {
        const parsed = new URL(value);
        return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch {
        return false;
    }
}

function displayShortUrl(url) {
    currentShortUrl = url;
    shortUrl.href = url;
    shortUrl.textContent = url;
    result.classList.remove("hidden");
}

async function shortenUrl() {
    if (!loggedInUser) {
        showMessage("Please log in to create a shortened URL.", true);
        window.location.href = "/login.html";
        return;
    }

    const url = urlInput.value.trim();

    if (!url) {
        showMessage("Please enter a URL.", true);
        return;
    }

    setButtonLoading(shortenBtn, true);
    try {
        const response = await fetch(`${API}/shorten`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });

        const resultData = await response.json();

        if (!response.ok) {
            throw new Error(resultData.error || "Could not shorten URL.");
        }

        displayShortUrl(resultData.data.short_url);
        showMessage("URL shortened successfully.");
        urlInput.value = "";

        await loadHistory();
        await loadStats();
    } catch (error) {
        showMessage(error.message, true);
    } finally {
        setButtonLoading(shortenBtn, false);
    }
}

async function loadHistory() {
    if (!loggedInUser) {
        historyBody.innerHTML = `<tr><td colspan="6"><a href="/login.html">Log in</a> to see your URL history.</td></tr>`;
        return;
    }

    const search = encodeURIComponent(searchInput.value.trim());

    try {
        const response = await fetch(`${API}/history?search=${search}`, { credentials: "include" });
        const resultData = await response.json();

        historyBody.innerHTML = "";

        const urlItems = resultData.data.filter(item => item.resource_type === "url");

        urlItems.forEach((item, index) => {
            const row = document.createElement("tr");
            const safeShortUrl = encodeURI(item.short_url);

            row.innerHTML = `
                <td>${index + 1}</td>
                <td title="${escapeHtml(item.original_url)}">
                    ${truncate(item.original_url, 45)}
                </td>
                <td>
                    <a href="${safeShortUrl}" target="_blank" rel="noopener noreferrer">
                        ${escapeHtml(item.short_code)}
                    </a>
                    <button type="button" data-copy="${escapeHtml(item.short_url)}">📋</button>
                </td>
                <td>${formatDate(item.created_at)}</td>
                <td>${item.click_count}</td>
                <td>
                    <div class="actions">
                        <button type="button" data-open="${escapeHtml(item.short_url)}">Open</button>
                        <button type="button" class="edit" data-edit="${item.id}">Edit</button>
                        <button type="button" class="delete" data-delete="${item.id}">Delete</button>
                    </div>
                </td>
            `;

            historyBody.appendChild(row);
        });

        if (urlItems.length === 0) {
            historyBody.innerHTML =
                `<tr><td colspan="6">No shortened URLs found. Manage images/videos/files from your <a href="/dashboard.html">Dashboard</a>.</td></tr>`;
        }
    } catch (error) {
        showMessage("Could not load history. Is Flask running?", true);
    }
}

async function editUrl(id) {
    try {
        const response = await fetch(`${API}/urls/${id}`, { credentials: "include" });
        const resultData = await response.json();

        if (!response.ok) throw new Error(resultData.error);

        const newUrl = prompt(
            "Edit original URL:",
            resultData.data.original_url
        );

        if (!newUrl || newUrl === resultData.data.original_url) return;

        const updateResponse = await fetch(`${API}/urls/${id}`, {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: newUrl.trim() })
        });

        const updated = await updateResponse.json();

        if (!updateResponse.ok) throw new Error(updated.error);

        showMessage("URL updated successfully.");
        await loadHistory();
        await loadStats();
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function deleteUrl(id) {
    if (!confirm("Delete this shortened URL?")) return;

    try {
        const response = await fetch(`${API}/urls/${id}`, {
            method: "DELETE",
            credentials: "include"
        });

        const resultData = await response.json();

        if (!response.ok) throw new Error(resultData.error);

        showMessage("URL deleted successfully.");
        await loadHistory();
        await loadStats();
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function clearHistory() {
    if (!loggedInUser) {
        showMessage("Please log in first.", true);
        return;
    }
    if (!confirm("Delete ALL of your URL/resource history? This cannot be undone.")) return;

    try {
        const response = await fetch(`${API}/history`, {
            method: "DELETE",
            credentials: "include"
        });

        if (!response.ok) throw new Error("Could not clear history.");

        result.classList.add("hidden");
        currentShortUrl = "";
        shortUrl.removeAttribute("href");
        shortUrl.textContent = "";
        showMessage("History cleared.");
        await loadHistory();
        await loadStats();
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API}/stats`, { credentials: "include" });
        const resultData = await response.json();

        document.getElementById("totalUrls").textContent = resultData.data.total_urls;
        document.getElementById("totalClicks").textContent = resultData.data.total_clicks;

        if (!loggedInUser) {
            document.getElementById("createdToday").textContent = 0;
            document.getElementById("activeLinks").textContent = 0;
            return;
        }

        const historyResponse = await fetch(`${API}/history`, { credentials: "include" });
        const historyData = await historyResponse.json();
        const urlItems = historyData.data.filter(item => item.resource_type === "url");

        const today = new Date().toISOString().slice(0, 10);
        const createdToday = urlItems.filter(item => item.created_at.startsWith(today)).length;

        document.getElementById("createdToday").textContent = createdToday;
        document.getElementById("activeLinks").textContent = resultData.data.total_urls;
    } catch (error) {
        console.error(error);
    }
}

function copyText(text) {
    if (!isHttpUrl(text)) {
        showMessage("No short URL available to copy.", true);
        return;
    }

    navigator.clipboard.writeText(text)
        .then(() => showMessage("Copied to clipboard."))
        .catch(() => showMessage("Could not copy URL.", true));
}

function openUrl(url) {
    const finalUrl = isHttpUrl(url) ? url : currentShortUrl;

    if (!isHttpUrl(finalUrl)) {
        showMessage("No short URL available. Shorten a URL first.", true);
        return;
    }

    const opened = window.open(finalUrl, "_blank", "noopener,noreferrer");
    if (!opened) {
        window.location.href = finalUrl;
    }
}

async function shareUrl() {
    if (!isHttpUrl(currentShortUrl)) {
        showMessage("Create a short URL first.", true);
        return;
    }

    if (navigator.share) {
        await navigator.share({
            title: "Short URL",
            url: currentShortUrl
        });
    } else {
        copyText(currentShortUrl);
    }
}

function truncate(value, length) {
    return value.length > length
        ? value.substring(0, length) + "..."
        : value;
}

shortenBtn.addEventListener("click", shortenUrl);
document.getElementById("copyBtn").addEventListener("click", () => copyText(currentShortUrl));
document.getElementById("openBtn").addEventListener("click", () => openUrl(currentShortUrl));
document.getElementById("shareBtn").addEventListener("click", shareUrl);
document.getElementById("quickCopy").addEventListener("click", () => copyText(currentShortUrl));
document.getElementById("quickOpen").addEventListener("click", () => openUrl(currentShortUrl));
document.getElementById("quickShare").addEventListener("click", shareUrl);
document.getElementById("refreshBtn").addEventListener("click", async (event) => {
    setButtonLoading(event.currentTarget, true);
    await Promise.all([loadHistory(), loadStats()]);
    setButtonLoading(event.currentTarget, false);
});
document.getElementById("historyRefresh").addEventListener("click", async (event) => {
    setButtonLoading(event.currentTarget, true);
    await loadHistory();
    setButtonLoading(event.currentTarget, false);
});
document.getElementById("clearBtn").addEventListener("click", clearHistory);

historyBody.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.dataset.copy) {
        copyText(target.dataset.copy);
    } else if (target.dataset.open) {
        openUrl(target.dataset.open);
    } else if (target.dataset.edit) {
        editUrl(Number(target.dataset.edit));
    } else if (target.dataset.delete) {
        deleteUrl(Number(target.dataset.delete));
    }
});

let searchTimer;
searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadHistory, 300);
});

async function boot() {
    loggedInUser = await renderAuthNav("navAuthSlot");
    await loadHistory();
    await loadStats();
}

boot();
