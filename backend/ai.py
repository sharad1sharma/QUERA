"""
AI features for the platform.

Everything here is designed to degrade gracefully: if no external AI
provider is configured (AI_API_KEY unset) or a call to it fails for any
reason, every endpoint falls back to transparent, rule-based/heuristic
logic that runs entirely on this app's own real data. Nothing here ever
fabricates statistics, and no AI output overrides a user's or admin's
Public/Private choice - recommendations are suggestions only.

Optional external provider: set AI_API_KEY in .env and install the
`anthropic` package (add it to requirements.txt yourself) to have the
Usage Assistant answer with a real model instead of the built-in FAQ
matcher. This is entirely optional; the app works fully without it.
"""
import os
import re
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

from auth import get_current_user, login_required, admin_required
from models import (
    get_resource_by_id, get_resources_for_owner, get_all_resources,
    update_resource_ai, get_resource_stats, get_ai_risk_distribution,
)

ai_api = Blueprint("ai_api", __name__)

AI_API_KEY = os.environ.get("AI_API_KEY")


def is_owner_or_admin(resource_row, user):
    if not user:
        return False
    if user["role"] == "admin":
        return True
    return resource_row["owner_id"] == user["id"]


# ---------------------------------------------------------------------------
# Optional external AI provider hook (used only by the Usage Assistant)
# ---------------------------------------------------------------------------

def call_external_ai(prompt):
    """Best-effort call to Cohere AI for free-form questions.
    Returns None on ANY failure so the caller always has a safe fallback."""
    if not AI_API_KEY:
        return None
    try:
        import cohere
        # Support both Cohere SDK v4 and v5
        try:
            # v5+ style (ClientV2)
            client = cohere.ClientV2(AI_API_KEY)
            response = client.chat(
                model="command-r-plus-08-2024",
                messages=[
                    {"role": "system", "content": ASSISTANT_CONTEXT},
                    {"role": "user", "content": prompt},
                ]
            )
            return response.message.content[0].text or None
        except AttributeError:
            # v4 style fallback
            client = cohere.Client(AI_API_KEY)
            response = client.chat(
                message=prompt,
                model="command-r-plus-08-2024",
            )
            return response.text or None
    except Exception as e:
        print(f"Cohere API Error: {e}")
        return None


# ---------------------------------------------------------------------------
# A. AI Usage Assistant
# ---------------------------------------------------------------------------

ASSISTANT_CONTEXT = (
    "You are the built-in help assistant for a URL/QR/file sharing platform. "
    "Users can shorten URLs and upload images, videos and files; every resource "
    "gets a short link (/s/<code>) and a QR code. Each resource can be Public "
    "(anyone with the link/QR, no login needed) or Private (only the owner and "
    "admins can access it). "
    "While you can help with the platform, you are also free to answer ANY general "
    "questions the user has, including providing app suggestions, general knowledge, "
    "or anything else they ask for."
)

FAQ = [
    (("qr", "generate qr", "create qr", "download qr"),
     "Every URL, image, video or file you create automatically gets a QR code. "
     "You'll see it right after creating the resource, and again as a thumbnail "
     "in the QR column of your Dashboard table - click it to open the full-size PNG."),
    (("private", "make it private", "hide"),
     "Open your Dashboard, find the resource in 'My Resources', and change its "
     "Visibility dropdown from Public to Private. Private resources can only be "
     "opened by you (the owner) or an admin - anyone else, including anonymous "
     "visitors, gets a 'This resource is private' page even with the correct link or QR."),
    (("public vs private", "difference between public and private", "public and private"),
     "Public: anyone with the short link or QR code can open it, no login required. "
     "Private: only the resource's owner and admins can open it - everyone else is blocked, "
     "and that check happens on the server, not just by hiding a button."),
    (("share video", "share a video"),
     "Upload the video from the Video tab on your Dashboard. You'll get a short link "
     "and QR code; opening the short link plays the video directly in the browser "
     "(range requests are supported, so seeking/scrubbing works)."),
    (("share file", "upload file", "share a document"),
     "Use the File tab on your Dashboard. The short link will either display or "
     "download the file depending on its type, and the QR code points to that same link."),
    (("delete", "remove a resource"),
     "Click Delete next to the resource in your Dashboard table. You can only delete "
     "your own resources; admins can delete any resource from the Admin Dashboard."),
    (("edit", "change url", "change destination"),
     "Click Edit next to a URL resource in your Dashboard to change its destination. "
     "Only the destination URL and visibility are editable, and only by the owner or an admin."),
    (("manage my resources", "my resources", "history"),
     "The 'My Resources' table on your Dashboard lists everything you've created, with "
     "search, visibility control, click counts, QR access, and edit/delete actions."),
    (("statistics", "stats", "clicks"),
     "Your Dashboard shows your own resource count, URL count and total clicks. "
     "Admins additionally see site-wide charts (by type, by visibility, over time, "
     "by user, and AI risk distribution) on the Admin Dashboard."),
]


def answer_from_faq(question):
    q = question.lower()
    for keywords, answer in FAQ:
        if any(k in q for k in keywords):
            return answer
    return (
        "I can help with using this platform - creating short links, QR codes, "
        "uploading images/videos/files, and managing Public/Private access. "
        "Could you rephrase your question, e.g. 'how do I make a file private?' "
        "or 'how do I share a video?'"
    )


@ai_api.post("/assistant")
@login_required
def assistant():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "Please ask a question."}), 400
    if len(question) > 500:
        return jsonify({"error": "Question is too long (max 500 characters)."}), 400

    external = call_external_ai(question)
    if external:
        return jsonify({"data": {"answer": external, "source": "ai"}})

    return jsonify({"data": {"answer": answer_from_faq(question), "source": "built-in assistant"}})


# ---------------------------------------------------------------------------
# B. AI Security Analysis (URLs)
# ---------------------------------------------------------------------------

SUSPICIOUS_KEYWORDS = (
    "login", "verify", "signin", "account", "secure", "update", "confirm",
    "password", "bank", "wallet", "gift", "prize", "free-", "urgent",
)
KNOWN_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly",
}


def analyze_url_risk(url):
    """Transparent heuristic risk scan. Not a guarantee of safety - clearly
    labeled as an AI-assisted recommendation to the user."""
    reasons = []
    score = 0
    try:
        parsed = urlparse(url)
    except Exception:
        return "medium", ["Could not parse the URL structure."]

    host = (parsed.hostname or "").lower()

    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
        score += 3
        reasons.append("Destination is a raw IP address rather than a domain name.")

    if "xn--" in host:
        score += 2
        reasons.append("Domain uses punycode, sometimes used to spoof lookalike domains.")

    if host.count(".") >= 3:
        score += 1
        reasons.append("Domain has an unusually deep subdomain structure.")

    lowered_url = url.lower()
    if any(k in lowered_url for k in SUSPICIOUS_KEYWORDS):
        score += 1
        reasons.append("URL text contains words often used in phishing attempts.")

    if host in KNOWN_SHORTENERS:
        score += 1
        reasons.append("Destination is itself a URL shortener, which can hide the final destination.")

    if parsed.scheme != "https":
        score += 1
        reasons.append("Destination does not use HTTPS.")

    if len(url) > 120:
        score += 1
        reasons.append("URL is unusually long.")

    if not reasons:
        reasons.append("No common phishing/malware indicators were detected in the URL text.")

    level = "high" if score >= 4 else "medium" if score >= 2 else "low"
    return level, reasons


@ai_api.get("/security/<int:resource_id>")
@login_required
def security_analysis(resource_id):
    row = get_resource_by_id(resource_id)
    user = get_current_user()

    if not row:
        return jsonify({"error": "Resource not found"}), 404
    if not is_owner_or_admin(row, user):
        return jsonify({"error": "You do not have permission to view this resource."}), 403
    if row["resource_type"] != "url":
        return jsonify({"error": "AI security analysis currently supports URL resources only."}), 400

    level, reasons = analyze_url_risk(row["original_url"])
    update_resource_ai(resource_id, ai_risk_level=level, ai_risk_reason="; ".join(reasons))

    return jsonify({"data": {
        "resource_id": resource_id,
        "risk_level": level,
        "reasons": reasons,
        "disclaimer": "AI-assisted heuristic analysis, not a guarantee of safety. Review the destination yourself before sharing widely.",
    }})


# ---------------------------------------------------------------------------
# C. AI Privacy Recommendation
# ---------------------------------------------------------------------------

SENSITIVE_NAME_HINTS = (
    "passport", "aadhaar", "aadhar", "ssn", "invoice", "salary", "payslip",
    "confidential", "private", "bank", "statement", "contract", "resume",
    "cv", "id_card", "id-card", "tax", "medical", "marksheet", "certificate",
    "license", "licence", "agreement", "nda",
)


def suggest_privacy(resource_row):
    reasons = []
    name = (resource_row["original_name"] or resource_row["original_url"] or "").lower()

    if any(hint in name for hint in SENSITIVE_NAME_HINTS):
        suggested = "private"
        reasons.append("The file/URL name contains a word commonly associated with personal or confidential documents.")
    else:
        suggested = "public"
        reasons.append("No indicators of sensitive content were found in the name.")

    return suggested, reasons


@ai_api.get("/privacy/<int:resource_id>")
@login_required
def privacy_recommendation(resource_id):
    row = get_resource_by_id(resource_id)
    user = get_current_user()

    if not row:
        return jsonify({"error": "Resource not found"}), 404
    if not is_owner_or_admin(row, user):
        return jsonify({"error": "You do not have permission to view this resource."}), 403

    suggested, reasons = suggest_privacy(row)
    update_resource_ai(resource_id, ai_privacy_suggestion=suggested, ai_privacy_reason="; ".join(reasons))

    return jsonify({"data": {
        "resource_id": resource_id,
        "recommended_visibility": suggested,
        "reasons": reasons,
        "note": "This is only a suggestion - you still choose the final Public/Private setting.",
    }})


# ---------------------------------------------------------------------------
# D. AI Analytics Insights (built only from real stored data)
# ---------------------------------------------------------------------------

def build_user_insights(rows):
    if not rows:
        return ["You haven't created any resources yet. Shorten a URL or upload a file to see insights here."]

    insights = []
    total_clicks = sum(r["click_count"] for r in rows)
    insights.append(f"You have {len(rows)} resource(s) with {total_clicks} total access(es) so far.")

    top = max(rows, key=lambda r: r["click_count"])
    if top["click_count"] > 0:
        label = top["original_name"] or top["original_url"] or top["short_code"]
        insights.append(f"Your most-accessed resource is '{label}' with {top['click_count']} access(es).")

    private_count = sum(1 for r in rows if r["visibility"] == "private")
    if private_count:
        insights.append(f"{private_count} of your resources are private (visible only to you and admins).")

    unused = [r for r in rows if r["click_count"] == 0]
    if unused:
        insights.append(f"{len(unused)} resource(s) have not been accessed yet - consider sharing their link or QR code.")

    return insights


@ai_api.get("/insights")
@login_required
def my_insights():
    user = get_current_user()
    rows = get_resources_for_owner(user["id"])
    return jsonify({"data": {"insights": build_user_insights(rows)}})


def build_admin_insights(stats, risk_distribution):
    insights = []
    insights.append(
        f"{stats['total_users']} user(s) have created {stats['total_resources']} resource(s) in total, "
        f"generating {stats['total_clicks']} access(es)."
    )
    if stats["total_resources"]:
        pub_pct = round(100 * stats["public_resources"] / stats["total_resources"])
        insights.append(f"{pub_pct}% of resources are Public and {100 - pub_pct}% are Private.")

    high_risk = next((r["count"] for r in risk_distribution if r["level"] == "high"), 0)
    if high_risk:
        insights.append(f"{high_risk} URL(s) are currently flagged as high AI-assessed risk and may warrant review.")

    return insights


@ai_api.get("/admin/insights")
@admin_required
def admin_insights():
    stats = get_resource_stats()
    risk_distribution = get_ai_risk_distribution()
    return jsonify({"data": {"insights": build_admin_insights(stats, risk_distribution)}})


@ai_api.get("/admin/risk-distribution")
@admin_required
def risk_distribution_endpoint():
    return jsonify({"data": get_ai_risk_distribution()})


# ---------------------------------------------------------------------------
# E. AI Resource Analysis (documented limitation)
# ---------------------------------------------------------------------------

@ai_api.get("/resource-analysis/<int:resource_id>")
@login_required
def resource_analysis(resource_id):
    """Basic, honest metadata-based classification. Real image/video content
    classification would require an external vision model - not implemented
    here; this is documented rather than faked. See README/setup.md."""
    row = get_resource_by_id(resource_id)
    user = get_current_user()

    if not row:
        return jsonify({"error": "Resource not found"}), 404
    if not is_owner_or_admin(row, user):
        return jsonify({"error": "You do not have permission to view this resource."}), 403

    notes = [f"Resource type: {row['resource_type']}."]
    if row["mime_type"]:
        notes.append(f"MIME type: {row['mime_type']}.")
    if row["original_name"]:
        notes.append(f"Original filename: {row['original_name']}.")

    return jsonify({"data": {
        "resource_id": resource_id,
        "notes": notes,
        "limitation": (
            "This is metadata-only analysis. Deep content classification (e.g. "
            "recognizing what is in an image or video) requires an external vision "
            "AI API, which is not configured in this deployment."
        ),
    }})
