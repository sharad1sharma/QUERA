// Shared across every page: figures out the API base URL and exposes small
// helpers for checking who is logged in and guarding pages.
const isLocalDevServer = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
// Always use relative /api when the page is served over HTTP/HTTPS (covers Vercel, any server).
// Only fall back to absolute localhost URL when opening the HTML file directly (file:// protocol).
const API = window.location.protocol.startsWith("http") ? "/api" : "http://localhost:5000/api";

async function fetchCurrentUser() {
    try {
        const response = await fetch(`${API}/auth/me`, { credentials: "include" });
        const result = await response.json();
        return result.data || null;
    } catch (error) {
        return null;
    }
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    }[char]));
}

function formatDate(value) {
    return new Date(value).toLocaleString();
}

async function logout() {
    await fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });
    window.location.href = "/login.html";
}

/**
 * Renders the right-hand side of the top nav depending on auth state.
 * `navSlotId` is the id of an element (usually inside <nav>) to fill in.
 */
async function renderAuthNav(navSlotId) {
    const slot = document.getElementById(navSlotId);
    if (!slot) return null;

    const user = await fetchCurrentUser();

    if (!user) {
        slot.innerHTML = `<a href="/login.html">Login</a><a href="/register.html">Register</a>`;
        return null;
    }

    const adminLink = user.role === "admin" ? `<a href="/admin.html">Admin</a>` : "";
    slot.innerHTML = `
        <a href="/dashboard.html">Dashboard</a>
        ${adminLink}
        <span class="nav-username">👤 ${escapeHtml(user.username)}</span>
        <a href="#" id="logoutLink">Logout</a>
    `;

    document.getElementById("logoutLink").addEventListener("click", (event) => {
        event.preventDefault();
        logout();
    });

    return user;
}

/** Redirects to /login.html if nobody is logged in. Returns the user or null. */
async function requireLogin() {
    const user = await fetchCurrentUser();
    if (!user) {
        window.location.href = "/login.html";
        return null;
    }
    return user;
}

/** Redirects away if the logged-in user isn't an admin. */
async function requireAdmin() {
    const user = await fetchCurrentUser();
    if (!user) {
        window.location.href = "/login.html";
        return null;
    }
    if (user.role !== "admin") {
        window.location.href = "/dashboard.html";
        return null;
    }
    return user;
}

/**
 * Shows/hides a small spinning loader inside a button without changing its
 * size (the button's fixed height/min-width from style.css keeps the
 * dimensions steady, matching the app's "same size" button system).
 *
 * Usage:
 *   setButtonLoading(submitBtn, true);   // before an async call
 *   setButtonLoading(submitBtn, false);  // in finally {}
 */
function setButtonLoading(button, isLoading) {
    if (!button) return;

    if (isLoading) {
        if (button.dataset.originalHtml === undefined) {
            button.dataset.originalHtml = button.innerHTML;
        }
        button.innerHTML = '<span class="btn-loader" aria-hidden="true"></span><span class="sr-only">Loading…</span>';
        button.disabled = true;
        button.classList.add("is-loading");
    } else {
        if (button.dataset.originalHtml !== undefined) {
            button.innerHTML = button.dataset.originalHtml;
            delete button.dataset.originalHtml;
        }
        button.disabled = false;
        button.classList.remove("is-loading");
    }
}
