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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
