import base64
import html
import json
import os
import random
import urllib.error
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
MAILCHIMP_AUDIENCE_ID = os.getenv("MAILCHIMP_AUDIENCE_ID", "4b72a551fe")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
APP_ORIGIN = os.getenv("APP_ORIGIN", "https://houlte.com")
APP_TITLE = os.getenv("APP_TITLE", "Houlte Email Agent")

app = Flask(__name__)
CORS(app)


def json_response(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False), status=status, content_type="application/json")


def esc(value):
    return html.escape(str(value or ""), quote=True)


def normalize_products(products):
    out = []
    if not isinstance(products, list):
        return out
    for p in products[:6]:
        if not isinstance(p, dict):
            continue
        out.append({
            "name": p.get("name") or p.get("title") or p.get("t") or "",
            "image": p.get("image") or p.get("img") or p.get("i") or "",
            "url": p.get("url") or p.get("u") or "https://www.houlte.com",
            "price": p.get("price") or p.get("p") or "",
            "category": p.get("category") or p.get("c") or "",
        })
    return out


def fallback_img(i=0):
    imgs = [
        "https://cdn.shopify.com/s/files/1/0717/7561/7279/files/HFDTU-2610_2.webp?v=1776334944",
        "https://cdn.shopify.com/s/files/1/0717/7561/7279/files/7_691c8900-87c7-43b2-b528-47401c5c6359.jpg?v=1776736018",
        "https://cdn.shopify.com/s/files/1/0717/7561/7279/files/HFSOU-2605_9.jpg?v=1776329283",
        "https://cdn.shopify.com/s/files/1/0717/7561/7279/files/4_8ce14210-0a1a-4494-8f96-8f0c3b716a33.jpg?v=1776916470",
        "https://cdn.shopify.com/s/files/1/0717/7561/7279/files/HFSBU-2606_2.jpg?v=1776337543",
    ]
    return imgs[i % len(imgs)]


def product_img(products, index):
    if len(products) > index and products[index].get("image"):
        return products[index]["image"]
    return fallback_img(index)


def product_name(products, index):
    if len(products) > index and products[index].get("name"):
        return products[index]["name"]
    return f"Houlte Curated Piece {index + 1}"


def product_url(products, index, landing_url):
    if len(products) > index and products[index].get("url"):
        return products[index]["url"]
    return landing_url


def get_palette(mood):
    ml = str(mood or "").lower()
    if "dark" in ml or "espresso" in ml:
        return {"bg":"#100805","panel":"#2c1c17","panel2":"#3B241C","text":"#FAF7F2","muted":"#CBB9A7","accent":"#D4A96A","cta":"#D4A96A","cta_text":"#100805","line":"#5A4034"}
    if "sage" in ml:
        return {"bg":"#EEF1EA","panel":"#DCE6D4","panel2":"#CBD9C0","text":"#1A2C14","muted":"#5F7357","accent":"#5A7C44","cta":"#3A5C2E","cta_text":"#EEF1EA","line":"#BECBB5"}
    if "ivory" in ml or "brass" in ml:
        return {"bg":"#FFFDF7","panel":"#F0E8DB","panel2":"#E5D8C4","text":"#2c1c17","muted":"#7A6A58","accent":"#B08A48","cta":"#2c1c17","cta_text":"#FFFDF7","line":"#E0D5C8"}
    if "forest" in ml:
        return {"bg":"#102016","panel":"#183221","panel2":"#254631","text":"#FAF7F2","muted":"#CAD6C3","accent":"#C7A76B","cta":"#FAF7F2","cta_text":"#102016","line":"#3C5B45"}
    return {"bg":"#FAF7F2","panel":"#EFE6DA","panel2":"#E2D2BE","text":"#2c1c17","muted":"#7E6253","accent":"#B8894A","cta":"#2c1c17","cta_text":"#FAF7F2","line":"#D8C8B5"}


def cta_button(label, url, pal):
    return f'''<a href="{esc(url)}" target="_blank" style="display:inline-block;background:{pal['cta']};color:{pal['cta_text']};text-decoration:none;padding:15px 28px;border-radius:999px;font-family:DM Sans,Arial,sans-serif;font-size:13px;letter-spacing:.12em;text-transform:uppercase;">{esc(label)}</a>'''


def poster_full_bleed(headline, subtitle, cta, landing_url, products, pal):
    img = product_img(products, 0)
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:{pal['bg']};"><tr><td style="padding:0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" background="{esc(img)}" style="background-image:linear-gradient(rgba(0,0,0,.42),rgba(0,0,0,.42)),url('{esc(img)}');background-size:cover;background-position:center;min-height:760px;"><tr><td style="padding:72px 46px 62px;min-height:760px;vertical-align:bottom;"><div style="font-family:DM Sans,Arial,sans-serif;color:#fff;font-size:12px;letter-spacing:.24em;text-transform:uppercase;margin-bottom:26px;">HOULTE</div><div style="font-family:Georgia,'Times New Roman',serif;color:#fff;font-size:58px;line-height:1.02;font-weight:400;margin-bottom:20px;max-width:520px;">{esc(headline)}</div><div style="font-family:DM Sans,Arial,sans-serif;color:rgba(255,255,255,.88);font-size:18px;line-height:1.55;max-width:470px;margin-bottom:34px;">{esc(subtitle)}</div>{cta_button(cta, landing_url, {'cta':'#FFFFFF','cta_text':'#2c1c17'})}</td></tr></table></td></tr></table>'''


def poster_rounded_grid(headline, subtitle, cta, landing_url, products, pal):
    img1, img2, img3 = product_img(products, 0), product_img(products, 1), product_img(products, 2)
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:{pal['bg']};"><tr><td style="padding:48px 34px;text-align:center;"><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['accent']};font-size:12px;letter-spacing:.24em;text-transform:uppercase;margin-bottom:18px;">HOULTE EDIT</div><div style="font-family:Georgia,'Times New Roman',serif;color:{pal['text']};font-size:50px;line-height:1.08;margin-bottom:16px;">{esc(headline)}</div><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:16px;line-height:1.62;margin:0 auto 32px;max-width:500px;">{esc(subtitle)}</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td width="58%" style="padding:7px;vertical-align:top;"><a href="{esc(product_url(products,0,landing_url))}" target="_blank"><img src="{esc(img1)}" alt="{esc(product_name(products,0))}" style="width:100%;height:430px;object-fit:cover;border-radius:24px;display:block;"></a></td><td width="42%" style="padding:7px;vertical-align:top;"><a href="{esc(product_url(products,1,landing_url))}" target="_blank"><img src="{esc(img2)}" alt="{esc(product_name(products,1))}" style="width:100%;height:205px;object-fit:cover;border-radius:24px;display:block;margin-bottom:14px;"></a><a href="{esc(product_url(products,2,landing_url))}" target="_blank"><img src="{esc(img3)}" alt="{esc(product_name(products,2))}" style="width:100%;height:205px;object-fit:cover;border-radius:24px;display:block;"></a></td></tr></table><div style="margin-top:34px;">{cta_button(cta, landing_url, pal)}</div></td></tr></table>'''


def poster_magazine(headline, subtitle, cta, landing_url, products, pal):
    img = product_img(products, 0)
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:{pal['bg']};"><tr><td style="padding:54px 42px 34px;"><table role="presentation" width="100%"><tr><td style="font-family:DM Sans,Arial,sans-serif;color:{pal['accent']};font-size:11px;letter-spacing:.28em;text-transform:uppercase;">HOULTE JOURNAL</td><td align="right" style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:11px;letter-spacing:.12em;text-transform:uppercase;">THE EDIT</td></tr></table><div style="border-top:1px solid {pal['line']};margin:18px 0 28px;"></div><div style="font-family:Georgia,'Times New Roman',serif;color:{pal['text']};font-size:64px;line-height:.98;letter-spacing:-.03em;max-width:540px;">{esc(headline)}</div><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:16px;line-height:1.7;max-width:440px;margin:22px 0 32px;">{esc(subtitle)}</div><img src="{esc(img)}" alt="{esc(product_name(products,0))}" style="width:100%;height:520px;object-fit:cover;display:block;border-radius:4px;"><table role="presentation" width="100%" style="margin-top:24px;"><tr><td style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:13px;line-height:1.5;">Curated furniture and lighting for rooms with quiet confidence.</td><td align="right">{cta_button(cta, landing_url, pal)}</td></tr></table></td></tr></table>'''


def poster_offer(headline, subtitle, cta, landing_url, products, pal, offer):
    img = product_img(products, 0)
    offer_text = offer or "LIMITED TIME"
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:{pal['bg']};"><tr><td style="padding:42px 34px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{pal['panel']};border-radius:28px;overflow:hidden;"><tr><td style="padding:38px 32px 28px;text-align:center;"><div style="display:inline-block;border:1px solid {pal['accent']};border-radius:999px;padding:8px 16px;font-family:DM Sans,Arial,sans-serif;color:{pal['accent']};font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-bottom:22px;">{esc(offer_text)}</div><div style="font-family:Georgia,'Times New Roman',serif;color:{pal['text']};font-size:54px;line-height:1.04;margin-bottom:16px;">{esc(headline)}</div><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:16px;line-height:1.6;max-width:480px;margin:0 auto 28px;">{esc(subtitle)}</div><img src="{esc(img)}" alt="{esc(product_name(products,0))}" style="width:100%;height:420px;object-fit:cover;border-radius:22px;display:block;margin-bottom:30px;">{cta_button(cta, landing_url, pal)}</td></tr></table></td></tr></table>'''


def poster_room_system(headline, subtitle, cta, landing_url, products, pal):
    top = ""
    bottom = ""
    for idx in range(5):
        img = product_img(products, idx)
        name = product_name(products, idx)
        url = product_url(products, idx, landing_url)
        cell = f'''<td width="{'50%' if idx < 2 else '33.33%'}" style="padding:6px;vertical-align:top;"><a href="{esc(url)}" target="_blank"><img src="{esc(img)}" alt="{esc(name)}" style="width:100%;height:{'300' if idx < 2 else '190'}px;object-fit:cover;border-radius:18px;display:block;"></a><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['text']};font-size:12px;line-height:1.35;margin-top:9px;">{esc(name)}</div></td>'''
        if idx < 2:
            top += cell
        else:
            bottom += cell
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:{pal['bg']};"><tr><td style="padding:46px 30px;"><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['accent']};font-size:12px;letter-spacing:.24em;text-transform:uppercase;text-align:center;margin-bottom:18px;">COMPLETE THE ROOM</div><div style="font-family:Georgia,'Times New Roman',serif;color:{pal['text']};font-size:52px;line-height:1.05;text-align:center;margin-bottom:16px;">{esc(headline)}</div><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:16px;line-height:1.6;text-align:center;max-width:510px;margin:0 auto 30px;">{esc(subtitle)}</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{top}</tr><tr>{bottom}</tr></table><div style="text-align:center;margin-top:32px;">{cta_button(cta, landing_url, pal)}</div></td></tr></table>'''


def poster_editorial_collage(headline, subtitle, cta, landing_url, products, pal):
    img1, img2, img3 = product_img(products, 0), product_img(products, 1), product_img(products, 2)
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:{pal['bg']};"><tr><td style="padding:38px 32px 46px;"><table role="presentation" width="100%"><tr><td width="48%" style="vertical-align:top;padding-right:10px;"><img src="{esc(img1)}" style="width:100%;height:430px;object-fit:cover;border-radius:120px 120px 18px 18px;display:block;"></td><td width="52%" style="vertical-align:top;padding-left:10px;"><div style="background:{pal['panel']};border-radius:22px;padding:28px 24px;margin-bottom:18px;"><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['accent']};font-size:11px;letter-spacing:.2em;text-transform:uppercase;margin-bottom:16px;">HOULTE</div><div style="font-family:Georgia,'Times New Roman',serif;color:{pal['text']};font-size:42px;line-height:1.05;margin-bottom:14px;">{esc(headline)}</div><div style="font-family:DM Sans,Arial,sans-serif;color:{pal['muted']};font-size:14px;line-height:1.6;">{esc(subtitle)}</div></div><table role="presentation" width="100%"><tr><td style="padding-right:6px;"><img src="{esc(img2)}" style="width:100%;height:170px;object-fit:cover;border-radius:18px;display:block;"></td><td style="padding-left:6px;"><img src="{esc(img3)}" style="width:100%;height:170px;object-fit:cover;border-radius:18px;display:block;"></td></tr></table></td></tr></table><div style="text-align:center;margin-top:30px;">{cta_button(cta, landing_url, pal)}</div></td></tr></table>'''


def generate_houlte_poster_html(data):
    headline = data.get("headline", "")
    subtitle = data.get("subtitle", "") or "A refined Houlte edit for rooms with depth, warmth, and quiet confidence."
    layout = data.get("layout", "Premium Mixed Variants")
    mood = data.get("mood", "Warm cream + walnut")
    cta = data.get("cta", "SHOP THE EDIT")
    landing_url = data.get("landing_url", "https://www.houlte.com")
    offer = data.get("offer", "")
    products = normalize_products(data.get("products", []))
    pal = get_palette(mood)
    if not headline:
        raise ValueError("Missing headline")
    chosen = layout
    if "Premium Mixed" in layout:
        chosen = random.choice(["Editorial Collage Story", "Full-Bleed Hero with Large Overlay", "Rounded Product Grid", "Magazine Poster", "Room System Poster"])
    if "Full-Bleed" in chosen:
        poster = poster_full_bleed(headline, subtitle, cta, landing_url, products, pal)
    elif "Rounded" in chosen or "Product Grid" in chosen:
        poster = poster_rounded_grid(headline, subtitle, cta, landing_url, products, pal)
    elif "Magazine" in chosen:
        poster = poster_magazine(headline, subtitle, cta, landing_url, products, pal)
    elif "Offer" in chosen:
        poster = poster_offer(headline, subtitle, cta, landing_url, products, pal, offer)
    elif "Room System" in chosen:
        poster = poster_room_system(headline, subtitle, cta, landing_url, products, pal)
    else:
        poster = poster_editorial_collage(headline, subtitle, cta, landing_url, products, pal)
    return poster.strip(), chosen


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
    if not (url.startswith("https://cdn.shopify.com") or url.startswith("https://houlte.com") or url.startswith("https://www.houlte.com")):
        return "forbidden", 403
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.houlte.com/"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return Response(r.read(), content_type=r.headers.get("Content-Type", "image/jpeg"), headers={"Cache-Control": "public, max-age=3600"})
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
            model = body.get("model") or "anthropic/claude-sonnet-4.5"
            if "/" not in model:
                model = "anthropic/claude-sonnet-4.5"
            req_data = json.dumps({"model": model, "messages": body.get("messages", []), "max_tokens": body.get("max_tokens", 1200), "temperature": body.get("temperature", 0.7)}).encode("utf-8")
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=req_data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {ANTHROPIC_API_KEY}", "HTTP-Referer": APP_ORIGIN, "X-Title": APP_TITLE}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                result = json.loads(r.read().decode("utf-8"))
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return json_response({"content": [{"type": "text", "text": content}], "raw": result})
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=request.get_data(), headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"}, method="POST")
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
    qs = request.query_string.decode()
    mc_url = f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/{mc_path}"
    if qs:
        mc_url += "?" + qs
    auth = base64.b64encode(f"key:{MAILCHIMP_API_KEY}".encode()).decode()
    try:
        req = urllib.request.Request(mc_url, data=request.get_data() or None, headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}", "User-Agent": "HoulteAgent/1.0"}, method=request.method)
        with urllib.request.urlopen(req, timeout=30) as r:
            response = Response(r.read(), status=r.status, content_type="application/json")
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
        req_data = json.dumps({"model": body.get("model", "google/gemini-2.5-flash-preview"), "messages": [{"role": "user", "content": body.get("prompt", "")}]}).encode("utf-8")
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=req_data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_API_KEY}", "HTTP-Referer": APP_ORIGIN, "X-Title": APP_TITLE}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode("utf-8"))
        return json_response({"success": True, "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""), "raw": result})
    except urllib.error.HTTPError as exc:
        return Response(exc.read(), status=exc.code, content_type="application/json")
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
        req = urllib.request.Request(webhook, data=request.get_data(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return Response(r.read(), content_type="application/json")
    except Exception as exc:
        return json_response({"error": str(exc)}, 500)


@app.route("/api/action-test", methods=["GET", "POST"])
def action_test():
    data = {"text": "browser test"} if request.method == "GET" else (request.get_json(silent=True) or {})
    return json_response({"ok": True, "message": "Houlte Agent Action is working", "received": data})


@app.route("/api/generate-email", methods=["POST"])
def generate_email():
    data = request.get_json(silent=True) or {}
    campaign = data.get("campaign", "")
    audience = data.get("audience", "")
    tone = data.get("tone", "sophisticated, warm, editorial")
    product_category = data.get("product_category", "")
    offer = data.get("offer", "")
    landing_url = data.get("landing_url", "https://www.houlte.com")
    subject = data.get("subject") or f"{campaign} | Houlte"
    preview = data.get("preview") or f"A design-led edit curated for {audience or 'your home'}."
    cta = data.get("cta", "Shop the Edit")
    body = f"""A beautiful home is built through thoughtful layers.

For this {campaign or 'Houlte edit'}, Houlte brings together {product_category or 'furniture and lighting'} pieces with a refined, editorial point of view. Each selection is designed to feel warm, elevated, and quietly timeless.

{offer if offer else ''}

Explore the edit and discover pieces made to bring depth, texture, and atmosphere into the room.

CTA: {cta}
Landing Page: {landing_url}"""
    return json_response({"ok": True, "subject": subject, "preview": preview, "body": body.strip(), "cta": cta, "tone": tone})


@app.route("/api/generate-plan", methods=["POST"])
def generate_plan():
    data = request.get_json(silent=True) or {}
    month = data.get("month", "")
    email_count = int(data.get("email_count", 12))
    events = data.get("events", "")
    categories = data.get("categories", []) or ["Lighting", "Dining", "Living Room"]
    audience = data.get("audience", "全体客户")
    send_times = ["Tuesday 10:00 AM EST", "Wednesday 10:00 AM EST", "Thursday 10:00 AM EST"]
    plan = []
    for i in range(1, email_count + 1):
        category = categories[(i - 1) % len(categories)]
        plan.append({"email_number": i, "suggested_date": f"{month} - Week {((i - 1) // 3) + 1}", "send_time": send_times[(i - 1) % len(send_times)], "theme": f"{category} Editorial Campaign", "type": "Editorial / Product Showcase" if i % 4 else "Room Edit", "audience": audience, "angle": f"Design-led story around {category}", "cta": "Shop the Edit"})
    return json_response({"ok": True, "month": month, "events": events, "plan": plan})


@app.route("/api/generate-poster-html", methods=["POST"])
def generate_poster_html():
    try:
        data = request.get_json(silent=True) or {}
        poster_html, chosen_layout = generate_houlte_poster_html(data)
        return json_response({"ok": True, "layout": chosen_layout, "requested_layout": data.get("layout", "Premium Mixed Variants"), "mood": data.get("mood", "Warm cream + walnut"), "poster_html": poster_html})
    except ValueError as exc:
        return json_response({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


def mailchimp_request(path, method="GET", payload=None):
    if not MAILCHIMP_API_KEY:
        raise RuntimeError("MAILCHIMP_API_KEY is not configured")
    url = f"https://{MAILCHIMP_DC}.api.mailchimp.com/3.0/{path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    auth = base64.b64encode(f"key:{MAILCHIMP_API_KEY}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}", "User-Agent": "HoulteAgent/1.0"}, method=method)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


@app.route("/api/create-mailchimp-draft", methods=["POST"])
def create_mailchimp_draft():
    data = request.get_json(silent=True) or {}
    subject = data.get("subject", "Houlte Campaign")
    preview = data.get("preview", "")
    from_name = data.get("from_name", "Houlte")
    reply_to = data.get("reply_to", "service@houlte.com")
    html_content = data.get("html") or data.get("poster_html", "")
    if not html_content:
        return json_response({"ok": False, "error": "Missing html or poster_html"}, 400)
    payload = {"type": "regular", "recipients": {"list_id": data.get("audience_id") or MAILCHIMP_AUDIENCE_ID}, "settings": {"subject_line": subject, "preview_text": preview, "title": subject, "from_name": from_name, "reply_to": reply_to, "auto_footer": False}}
    try:
        campaign = mailchimp_request("/campaigns", "POST", payload)
        campaign_id = campaign.get("id")
        if not campaign_id:
            return json_response({"ok": False, "error": "Mailchimp did not return campaign id", "raw": campaign}, 500)
        mailchimp_request(f"/campaigns/{campaign_id}/content", "PUT", {"html": html_content})
        web_id = campaign.get("web_id")
        edit_url = f"https://{MAILCHIMP_DC}.admin.mailchimp.com/campaigns/edit?id={web_id}" if web_id else ""
        return json_response({"ok": True, "campaign_id": campaign_id, "web_id": web_id, "edit_url": edit_url, "subject": subject})
    except urllib.error.HTTPError as exc:
        return json_response({"ok": False, "error": exc.read().decode("utf-8", errors="replace")}, exc.code)
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc)}, 500)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
