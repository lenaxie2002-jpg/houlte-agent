import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_HTML = BASE_DIR / "static" / "houlte_email_agent.html"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY", "")
MAILCHIMP_DC = os.getenv("MAILCHIMP_DC", "us9")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
APP_ORIGIN = os.getenv("APP_ORIGIN", "https://houlte.com")
APP_TITLE = os.getenv("APP_TITLE", "Houlte Email Agent")

app = Flask(__name__)
CORS(app)


def json_response(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False), status=status, content_type="application/json")


@app.get("/")
def index():
    return send_file(STATIC_HTML)


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "houlte-email-agent"})


@app.get("/api/img")
def img_proxy():
    url = request.args.get("url", "")
    if not url:
        return "missing url", 400
    if not (
        url.startswith("https://cdn.shopify.com")
        or url.startswith("https://houlte.com")
        or url.startswith("https://www.houlte.com")
    ):
        return "forbidden", 403
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.houlte.com/"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            content_type = r.headers.get("Content-Type", "image/jpeg")
            data = r.read()
        return Response(data, content_type=content_type, headers={"Cache-Control": "public, max-age=3600"})
    except Exception as exc:
        return f"error: {exc}", 502


@app.route("/api/claude", methods=["POST", "OPTIONS"])
def claude_proxy():
    if request.method == "OPTIONS":
        return Response(status=204)
    if not ANTHROPIC_API_KEY:
        return json_response({"error": "ANTHROPIC_API_KEY is not configured"}, 500)
    try:
        body = request.get_json(force=True) or {}
        if ANTHROPIC_API_KEY.startswith("sk-or-v1-"):
            messages = body.get("messages", [])
            model = body.get("model") or "anthropic/claude-sonnet-4.5"
            if "/" not in model:
                model = "anthropic/claude-sonnet-4.5"
            req_data = json.dumps(
                {
                    "model": model,
                    "messages": messages,
                    "max_tokens": body.get("max_tokens", 1200),
                    "temperature": body.get("temperature", 0.7),
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {ANTHROPIC_API_KEY}",
                    "HTTP-Referer": APP_ORIGIN,
                    "X-Title": APP_TITLE,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                result = json.loads(r.read().decode("utf-8"))
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return json_response({"content": [{"type": "text", "text": content}], "raw": result})

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=request.get_data(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return Response(r.read(), content_type="application/json")
    except urllib.error.HTTPError as exc:
        return Response(exc.read(), status=exc.code, content_type="application/json")
    except Exception as exc:
        return json_response({"error": str(exc)}, 500)


@app.route("/api/mailchimp/", defaults={"mc_path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.route("/api/mailchimp/<path:mc_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def mailchimp_proxy(mc_path):
    if request.method == "OPTIONS":
        resp = Response(status=204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return resp
    if not MAILCHIMP_API_KEY:
        return json_response({"error": "MAILCHIMP_API_KEY is not configured"}, 500)

    query_string = request.query_string.decode()
    mc_url = f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/{mc_path}"
    if query_string:
        mc_url += "?" + query_string
    auth = base64.b64encode(f"key:{MAILCHIMP_API_KEY}".encode()).decode()
    body_data = request.get_data()
    try:
        req = urllib.request.Request(
            mc_url,
            data=body_data if body_data else None,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
                "User-Agent": "HoulteAgent/1.0",
            },
            method=request.method,
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            resp_data = r.read()
            response = Response(resp_data, status=r.status, content_type="application/json")
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
    except urllib.error.HTTPError as exc:
        response = Response(exc.read(), status=exc.code, content_type="application/json")
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    except Exception as exc:
        return json_response({"error": str(exc)}, 500)


@app.route("/api/generate-image", methods=["POST", "OPTIONS"])
def image_gen_proxy():
    if request.method == "OPTIONS":
        resp = Response(status=204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    if not OPENROUTER_API_KEY:
        return json_response({"error": "OPENROUTER_API_KEY is not configured"}, 500)
    try:
        body = request.get_json(force=True) or {}
        prompt_text = body.get("prompt", "")
        model = body.get("model", "google/gemini-2.5-flash-preview")
        req_data = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt_text}]}).encode("utf-8")
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": APP_ORIGIN,
                "X-Title": APP_TITLE,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode("utf-8"))
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        response = json_response({"success": True, "content": content, "raw": result})
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    except urllib.error.HTTPError as exc:
        response = Response(exc.read(), status=exc.code, content_type="application/json")
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    except Exception as exc:
        return json_response({"error": str(exc)}, 500)


@app.route("/api/feishu", methods=["POST", "OPTIONS"])
def feishu_proxy():
    if request.method == "OPTIONS":
        return Response(status=204)
    webhook = request.headers.get("X-Webhook") or FEISHU_WEBHOOK
    if not webhook:
        return json_response({"error": "FEISHU_WEBHOOK is not configured"}, 500)
    try:
        req = urllib.request.Request(
            webhook,
            data=request.get_data(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return Response(r.read(), content_type="application/json")
    except Exception as exc:
        return json_response({"error": str(exc)}, 500)


@app.route("/api/action-test", methods=["GET", "POST"])
def action_test():
    if request.method == "GET":
        data = {"text": "browser test"}
    else:
        data = request.get_json(silent=True) or {}

    return json_response({
        "ok": True,
        "message": "Houlte Agent Action is working",
        "received": data
    })
    

@app.route("/api/generate-email", methods=["POST"])
def generate_email():
    data = request.get_json(silent=True) or {}

    campaign = data.get("campaign", "")
    audience = data.get("audience", "")
    tone = data.get("tone", "friendly")

    email_subject = f"{campaign} | Houlte"

    email_body = f"""
Hi {audience},

We're excited to share our latest {campaign} collection with you.

Crafted with elegance and timeless detail, this campaign reflects the spirit of Houlte.

Explore the collection today.

Best,
Houlte Team
"""

    return json_response({
        "ok": True,
        "subject": email_subject,
        "body": email_body,
        "tone": tone
    })


@app.route("/api/generate-plan", methods=["POST"])
def generate_plan():
    data = request.get_json(silent=True) or {}

    month = data.get("month", "")
    email_count = data.get("email_count", 12)
    events = data.get("events", "")
    categories = data.get("categories", [])
    audience = data.get("audience", "全体客户")

    plan = []
    for i in range(1, int(email_count) + 1):
        category = categories[(i - 1) % len(categories)] if categories else "Lighting"
        plan.append({
            "email_number": i,
            "suggested_date": f"{month} - Week {((i - 1) // 3) + 1}",
            "theme": f"{category} Editorial Campaign",
            "type": "Editorial / Product Showcase",
            "audience": audience,
            "angle": f"Design-led story around {category}",
            "cta": "Shop the Edit"
        })

    return json_response({
        "ok": True,
        "month": month,
        "events": events,
        "plan": plan
    })


@app.route("/api/generate-email", methods=["POST"])
def generate_email():
    data = request.get_json(silent=True) or {}

    campaign = data.get("campaign", "")
    audience = data.get("audience", "")
    tone = data.get("tone", "sophisticated, warm, editorial")
    product_category = data.get("product_category", "")
    offer = data.get("offer", "")
    landing_url = data.get("landing_url", "")

    subject = f"{campaign} | Houlte"
    preview = f"A design-led edit curated for {audience or 'your home'}."

    body = f"""
A beautiful home is built through thoughtful layers.

For this {campaign}, Houlte brings together {product_category or 'furniture and lighting'} pieces with a refined, editorial point of view. Each selection is designed to feel warm, elevated, and quietly timeless.

{offer if offer else ''}

Explore the edit and discover pieces made to bring depth, texture, and atmosphere into the room.

CTA: Shop the Edit
Landing Page: {landing_url or 'https://www.houlte.com'}
"""

    return json_response({
        "ok": True,
        "subject": subject,
        "preview": preview,
        "body": body.strip(),
        "tone": tone
    })

@app.route("/api/generate-poster-html", methods=["POST"])
def generate_poster_html():
    data = request.get_json(silent=True) or {}

    headline = data.get("headline", "")
    subtitle = data.get("subtitle", "")
    layout = data.get("layout", "Premium Mixed Variants")
    mood = data.get("mood", "Warm cream + walnut")
    cta = data.get("cta", "SHOP THE EDIT")
    landing_url = data.get("landing_url", "https://www.houlte.com")
    products = data.get("products", [])

    if not headline:
        return json_response({"ok": False, "error": "Missing headline"}, 400)

    ml = mood.lower()
    pal = {
        "bg": "#FAF7F2",
        "card": "#EDE5D8",
        "text": "#2c1c17",
        "muted": "rgba(44,28,23,0.68)",
        "accent": "#b8894a",
        "cta": "#2c1c17",
        "cta_text": "#FAF7F2"
    }

    if "dark" in ml or "espresso" in ml:
        pal = {
            "bg": "#120803",
            "card": "#2c1c17",
            "text": "#FAF7F2",
            "muted": "rgba(250,247,242,0.72)",
            "accent": "#d4a96a",
            "cta": "#d4a96a",
            "cta_text": "#120803"
        }
    elif "sage" in ml or "green" in ml:
        pal = {
            "bg": "#EEF1EA",
            "card": "#DAE5D0",
            "text": "#1a2c14",
            "muted": "rgba(26,44,20,0.72)",
            "accent": "#5a7c44",
            "cta": "#3a5c2e",
            "cta_text": "#EEF1EA"
        }

    def product_img(index):
        if len(products) > index:
            return products[index].get("image", "")
        return ""

    img1 = product_img(0)
    img2 = product_img(1)
    img3 = product_img(2)

    if "Full-Bleed" in layout:
        poster_html = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="background:{pal['bg']};max-width:660px;margin:0 auto;">
  <tr>
    <td style="padding:0;">
      <div style="background:url('{img1}') center/cover no-repeat;min-height:720px;position:relative;">
        <div style="background:rgba(0,0,0,.38);min-height:720px;padding:64px 42px;box-sizing:border-box;">
          <div style="font-family:DM Sans,Arial,sans-serif;color:#fff;font-size:12px;letter-spacing:.22em;text-transform:uppercase;margin-bottom:24px;">HOULTE</div>
          <div style="font-family:Georgia,serif;color:#fff;font-size:54px;line-height:1.05;margin-bottom:20px;">{headline}</div>
          <div style="font-family:DM Sans,Arial,sans-serif;color:rgba(255,255,255,.86);font-size:18px;line-height:1.55;max-width:460px;">{subtitle}</div>
          <a href="{landing_url}" style="display:inline-block;margin-top:34px;background:#fff;color:#2c1c17;text-decoration:none;padding:15px 26px;border-radius:999px;font-family:DM Sans,Arial,sans-serif;font-size:13px;letter-spacing:.12em;">{cta}</a>
        </div>
      </div>
    </td>
  </tr>
</table>
"""
    else:
        poster_html = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="background:{pal['bg']};max-width:660px;margin:0 auto;">
  <tr>
    <td style="padding:46px 34px;text-align:center;">
      <div style="font-family:DM Sans,Arial,sans-serif;color:{pal['accent']};font-size:12px;letter-spacing:.22em;text-transform:uppercase;margin-bottom:18px;">HOULTE EDIT</div>
      <div style="font-family:Georgia,serif;color:{pal['text']};font-size:48px;line-height:1.08;margin-bottom:16px;">{headline}</div>
      <div style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:16px;line-height:1.6;margin:0 auto 30px;max-width:500px;">{subtitle}</div>

      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="58%" style="padding:6px;">
            <img src="{img1}" style="width:100%;height:auto;border-radius:20px;display:block;">
          </td>
          <td width="42%" style="padding:6px;">
            <img src="{img2}" style="width:100%;height:auto;border-radius:20px;display:block;margin-bottom:12px;">
            <img src="{img3}" style="width:100%;height:auto;border-radius:20px;display:block;">
          </td>
        </tr>
      </table>

      <a href="{landing_url}" style="display:inline-block;margin-top:32px;background:{pal['cta']};color:{pal['cta_text']};text-decoration:none;padding:15px 28px;border-radius:999px;font-family:DM Sans,Arial,sans-serif;font-size:13px;letter-spacing:.12em;">{cta}</a>
    </td>
  </tr>
</table>
"""

    return json_response({
        "ok": True,
        "layout": layout,
        "mood": mood,
        "poster_html": poster_html.strip()
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
