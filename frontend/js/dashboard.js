let currentUser = null;

const TYPE_ICONS = { url: "🔗", image: "🖼️", video: "🎬", file: "📄" };

async function init() {
    currentUser = await requireLogin();
    if (!currentUser) return;
    await renderAuthNav("navAuthSlot");
    await loadResources();
}

// --- Tab switching -----------------------------------------------------

document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        document.querySelectorAll(".create-form").forEach(form => {
            form.classList.toggle("hidden", form.dataset.panel !== btn.dataset.tab);
        });
        document.getElementById("createMessage").textContent = "";
    });
});

// --- Helpers ------------------------------------------------------------

function showMessage(text, error = false) {
    const message = document.getElementById("createMessage");
    message.textContent = text;
    message.style.color = error ? "#d32f2f" : "#15934a";
}

function showResult(data) {
    document.getElementById("result").classList.remove("hidden");
    const link = document.getElementById("shortUrl");
    link.href = data.short_url;
    link.textContent = data.short_url;

    const qr = document.getElementById("qrPreview");
    if (data.qr_url) {
        qr.src = data.qr_url;
        qr.classList.remove("hidden");
    } else {
        qr.classList.add("hidden");
    }

    document.getElementById("copyBtn").onclick = () => {
        navigator.clipboard.writeText(data.short_url)
            .then(() => showMessage("Copied to clipboard."))
            .catch(() => showMessage("Could not copy.", true));
    };
}

// --- Create: URL ----------------------------------------------------------

document.getElementById("urlForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const url = document.getElementById("urlInput").value.trim();
    const visibility = document.getElementById("urlVisibility").value;
    const submitBtn = event.target.querySelector("button[type=submit]");

    setButtonLoading(submitBtn, true);
    try {
        const response = await fetch(`${API}/shorten`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, visibility })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);

        showMessage("URL shortened successfully.");
        showResult(result.data);
        document.getElementById("urlInput").value = "";
        await loadResources();
    } catch (error) {
        showMessage(error.message, true);
    } finally {
        setButtonLoading(submitBtn, false);
    }
});

// --- Create: Image / Video / File (shared upload logic) -------------------

function wireUploadForm(formId, inputId, visibilityId, resourceType) {
    document.getElementById(formId).addEventListener("submit", async (event) => {
        event.preventDefault();
        const fileInput = document.getElementById(inputId);
        const visibility = document.getElementById(visibilityId).value;

        if (!fileInput.files.length) {
            showMessage("Please choose a file.", true);
            return;
        }

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        formData.append("visibility", visibility);

        const submitBtn = event.target.querySelector("button[type=submit]");
        setButtonLoading(submitBtn, true);
        try {
            const response = await fetch(`${API}/resources/${resourceType}`, {
                method: "POST",
                credentials: "include",
                body: formData
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);

            showMessage(`${resourceType} uploaded successfully.`);
            showResult(result.data);
            fileInput.value = "";
            await loadResources();
        } catch (error) {
            showMessage(error.message, true);
        } finally {
            setButtonLoading(submitBtn, false);
        }
    });
}

wireUploadForm("imageForm", "imageInput", "imageVisibility", "image");
wireUploadForm("videoForm", "videoInput", "videoVisibility", "video");
wireUploadForm("fileForm", "fileInput", "fileVisibility", "file");

// --- AI Assistant -----------------------------------------------------

/**
 * Converts a simple markdown string into safe HTML.
 * Supports: **bold**, *italic*, `code`, ```code blocks```,
 * # headings (h1-h3), - bullet lists, numbered lists, blank-line paragraphs.
 */
function renderMarkdown(text) {
    // Escape raw HTML first to prevent XSS
    const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

    // Preserve code blocks before other substitutions
    const codeBlocks = [];
    text = text.replace(/```[\s\S]*?```/g, match => {
        const inner = match.slice(3, -3).replace(/^[a-z]*\n/, ""); // strip language tag
        codeBlocks.push(`<pre class="ai-code-block"><code>${esc(inner.trim())}</code></pre>`);
        return `@@CODEBLOCK${codeBlocks.length - 1}@@`;
    });

    // Process line-by-line
    const lines = text.split("\n");
    const out = [];
    let inList = false;
    let listType = null;

    const closeLists = () => {
        if (inList) { out.push(listType === "ul" ? "</ul>" : "</ol>"); inList = false; listType = null; }
    };

    for (let line of lines) {
        // Headings
        const h3 = line.match(/^###\s+(.+)/);
        const h2 = line.match(/^##\s+(.+)/);
        const h1 = line.match(/^#\s+(.+)/);
        if (h3) { closeLists(); out.push(`<h4>${esc(h3[1])}</h4>`); continue; }
        if (h2) { closeLists(); out.push(`<h3>${esc(h2[1])}</h3>`); continue; }
        if (h1) { closeLists(); out.push(`<h3>${esc(h1[1])}</h3>`); continue; }

        // Numbered list
        const num = line.match(/^\d+\.\s+(.+)/);
        if (num) {
            if (!inList || listType !== "ol") { closeLists(); out.push("<ol>"); inList = true; listType = "ol"; }
            out.push(`<li>${inlineFormat(esc(num[1]))}</li>`);
            continue;
        }

        // Bullet list (-, *, +)
        const bullet = line.match(/^[\-\*\+]\s+(.+)/);
        if (bullet) {
            if (!inList || listType !== "ul") { closeLists(); out.push("<ul>"); inList = true; listType = "ul"; }
            out.push(`<li>${inlineFormat(esc(bullet[1]))}</li>`);
            continue;
        }

        // Blank line — only close the list if the NEXT non-empty line is NOT another list item
        // (Cohere often puts blank lines between numbered items, which was resetting to "1.")
        if (line.trim() === "") {
            const nextContent = lines.slice(lines.indexOf(line) + 1).find(l => l.trim() !== "") || "";
            const nextIsOl = /^\d+\.\s/.test(nextContent);
            const nextIsUl = /^[\-\*\+]\s/.test(nextContent);
            if (inList && ((listType === "ol" && nextIsOl) || (listType === "ul" && nextIsUl))) {
                // Skip blank line — stay in the same list
                continue;
            }
            closeLists();
            out.push("");
            continue;
        }

        // Normal line
        closeLists();
        out.push(`<p>${inlineFormat(esc(line))}</p>`);
    }
    closeLists();

    let html = out.join("\n");

    // Restore code blocks
    codeBlocks.forEach((block, i) => { html = html.replace(`@@CODEBLOCK${i}@@`, block); });

    return html;
}

/** Apply inline markdown: **bold**, *italic*, `code` */
function inlineFormat(s) {
    return s
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

document.getElementById("aiAssistantForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("aiQuestion");
    const question = input.value.trim();
    const answerBox = document.getElementById("aiAnswer");
    if (!question) return;

    const submitBtn = event.target.querySelector("button[type=submit]");
    setButtonLoading(submitBtn, true);
    answerBox.classList.remove("hidden");
    answerBox.innerHTML = `<span class="ai-thinking">⏳ Thinking…</span>`;
    try {
        const response = await fetch(`${API}/ai/assistant`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);
        answerBox.innerHTML = renderMarkdown(result.data.answer);
    } catch (error) {
        answerBox.innerHTML = `<span style="color:#d32f2f">❌ Sorry, I couldn't answer that: ${escapeHtml(error.message)}</span>`;
    } finally {
        setButtonLoading(submitBtn, false);
    }
});

// --- List / manage resources ---------------------------------------------

const RISK_ICONS = { low: "🟢", medium: "🟡", high: "🔴" };

function aiBadge(item) {
    if (item.resource_type === "url" && item.ai_risk_level) {
        const icon = RISK_ICONS[item.ai_risk_level] || "⚪";
        const reason = escapeHtml(item.ai_risk_reason || "");
        return `<span class="ai-badge" title="${reason}">${icon} ${item.ai_risk_level} risk</span>`;
    }
    if (item.ai_privacy_suggestion && item.ai_privacy_suggestion !== item.visibility) {
        const reason = escapeHtml(item.ai_privacy_reason || "");
        return `<span class="ai-badge ai-badge-suggest" title="${reason}">💡 suggests ${item.ai_privacy_suggestion}</span>`;
    }
    return "-";
}

async function loadResources() {
    const search = encodeURIComponent(document.getElementById("searchInput").value.trim());
    const body = document.getElementById("resourceBody");

    try {
        const response = await fetch(`${API}/history?search=${search}`, { credentials: "include" });
        const result = await response.json();
        const rows = result.data || [];

        body.innerHTML = "";
        rows.forEach((item, index) => {
            const tr = document.createElement("tr");
            const label = item.resource_type === "url"
                ? escapeHtml(item.original_url)
                : escapeHtml(item.original_name || "unnamed");

            tr.innerHTML = `
                <td>${index + 1}</td>
                <td>${TYPE_ICONS[item.resource_type] || ""} ${item.resource_type}</td>
                <td title="${label}">${label.length > 40 ? label.slice(0, 40) + "..." : label}</td>
                <td><a href="${item.short_url}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.short_url)}</a></td>
                <td>
                    <select class="visibility-select" data-id="${item.id}">
                        <option value="public" ${item.visibility === "public" ? "selected" : ""}>🌐 Public</option>
                        <option value="private" ${item.visibility === "private" ? "selected" : ""}>🔒 Private</option>
                    </select>
                </td>
                <td>${item.click_count}</td>
                <td>${aiBadge(item)}</td>
                <td>${item.qr_url ? `<a href="${item.qr_url}" target="_blank"><img class="qr-thumb" src="${item.qr_url}" alt="QR"></a>` : "-"}</td>
                <td>
                    <div class="actions">
                        ${item.resource_type === "url" ? `<button class="edit" data-edit="${item.id}">Edit</button>` : ""}
                        <button class="delete" data-delete="${item.id}">Delete</button>
                    </div>
                </td>
            `;
            body.appendChild(tr);
        });

        if (rows.length === 0) {
            body.innerHTML = `<tr><td colspan="9">No resources yet. Create one above.</td></tr>`;
        }

        document.getElementById("statResources").textContent = rows.length;
        document.getElementById("statUrls").textContent = rows.filter(r => r.resource_type === "url").length;
        document.getElementById("statClicks").textContent = rows.reduce((sum, r) => sum + r.click_count, 0);
    } catch (error) {
        body.innerHTML = `<tr><td colspan="8">Could not load your resources.</td></tr>`;
    }
}

document.getElementById("resourceBody").addEventListener("change", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !target.classList.contains("visibility-select")) return;

    const id = target.dataset.id;
    const visibility = target.value;

    try {
        const response = await fetch(`${API}/urls/${id}`, {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ visibility })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);
        showMessage("Visibility updated.");
    } catch (error) {
        showMessage(error.message, true);
        await loadResources();
    }
});

document.getElementById("resourceBody").addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.dataset.edit) {
        await editResource(Number(target.dataset.edit));
    } else if (target.dataset.delete) {
        await deleteResource(Number(target.dataset.delete));
    }
});

async function editResource(id) {
    try {
        const response = await fetch(`${API}/urls/${id}`, { credentials: "include" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);

        const newUrl = prompt("Edit destination URL:", result.data.original_url);
        if (!newUrl || newUrl === result.data.original_url) return;

        const updateResponse = await fetch(`${API}/urls/${id}`, {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: newUrl.trim() })
        });
        const updated = await updateResponse.json();
        if (!updateResponse.ok) throw new Error(updated.error);

        showMessage("Resource updated.");
        await loadResources();
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function deleteResource(id) {
    if (!confirm("Delete this resource? This cannot be undone.")) return;

    try {
        const response = await fetch(`${API}/urls/${id}`, { method: "DELETE", credentials: "include" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);

        showMessage("Resource deleted.");
        await loadResources();
    } catch (error) {
        showMessage(error.message, true);
    }
}

document.getElementById("refreshBtn").addEventListener("click", async (event) => {
    setButtonLoading(event.currentTarget, true);
    await loadResources();
    setButtonLoading(event.currentTarget, false);
});

let searchTimer;
document.getElementById("searchInput").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadResources, 300);
});

init();
