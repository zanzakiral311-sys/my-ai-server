import os
import json
import hmac
import time
import secrets
from datetime import date
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel
import anthropic

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    messages: list[dict]
    search: bool = True
    style: str = "short"
    attachment: Optional[dict] = None

class ImageRequest(BaseModel):
    prompt: str
    quality: str = "normal"

class TranslateRequest(BaseModel):
    lang: str
    strings: dict

LANG_NAMES = {
    "hi": "Hindi", "ur": "Urdu", "ne": "Nepali", "si": "Sinhala", "ta": "Tamil",
    "ms": "Malay", "id": "Indonesian", "th": "Thai", "vi": "Vietnamese",
    "zh": "Chinese (Simplified)", "ja": "Japanese", "ko": "Korean", "ar": "Arabic",
    "tr": "Turkish", "fa": "Persian", "fr": "French", "de": "German", "it": "Italian",
    "es": "Spanish", "pt": "Portuguese", "ru": "Russian", "nl": "Dutch", "pl": "Polish",
    "sv": "Swedish", "tl": "Filipino", "sw": "Swahili",
}
TR_CACHE = {}
TR_USE = {"day": "", "ips": {}}

STYLES = {
    "short": "উত্তর সংক্ষিপ্ত ও সরাসরি রাখো।",
    "long": "উত্তর বিস্তারিত ও ধাপে ধাপে ব্যাখ্যা করে দাও।",
}

STATS = {"day": str(date.today()), "ips": {}, "total": 0, "blocked": 0, "all": 0}

def reset_if_new_day():
    d = str(date.today())
    if STATS["day"] != d:
        STATS["day"] = d
        STATS["ips"] = {}
        STATS["total"] = 0
        STATS["blocked"] = 0

def client_ip(request: Request):
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def text_of(resp):
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

NOCACHE = {"Cache-Control": "no-cache, must-revalidate"}

@app.get("/")
def home():
    return FileResponse("index.html", headers=NOCACHE)

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")

@app.get("/logo.png")
def logo():
    names = sorted(os.listdir("."))
    pick = None
    for n in names:
        if n.lower().startswith("logo") and n.lower().endswith(IMG_EXT):
            pick = n
            break
    if not pick:
        for n in names:
            if n.lower().endswith(IMG_EXT):
                pick = n
                break
    if pick:
        return FileResponse(pick, headers={"Cache-Control": "public, max-age=3600"})
    return JSONResponse({"detail": "Not Found"}, status_code=404)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/privacy")
def privacy():
    return FileResponse("privacy.html", headers=NOCACHE)

@app.get("/admin")
def admin(key: str = ""):
    ak = os.environ.get("ADMIN_KEY", "")
    if not ak or not hmac.compare_digest(key.encode(), ak.encode()):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    reset_if_new_day()
    mode = "চালু (মেসেজ বন্ধ)" if os.environ.get("MAINTENANCE", "").lower() == "on" else "বন্ধ (সব স্বাভাবিক)"
    html = f"""<!DOCTYPE html>
<html lang="bn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin</title>
<style>body{{font-family:sans-serif;padding:16px;line-height:2}}</style></head><body>
<h2>অ্যাডমিন</h2>
<p>তারিখ: {STATS['day']}</p>
<p>আজ মোট মেসেজ: <b>{STATS['total']}</b></p>
<p>আজ আলাদা ব্যবহারকারী (আইপি): <b>{len(STATS['ips'])}</b></p>
<p>সীমা ছাড়ানোয় আটকানো: <b>{STATS['blocked']}</b></p>
<p>সার্ভার চালুর পর মোট: <b>{STATS['all']}</b></p>
<p>দৈনিক সীমা (প্রতি আইপি): <b>{os.environ.get('DAILY_LIMIT', '30')}</b></p>
<p>রক্ষণাবেক্ষণ মোড: <b>{mode}</b></p>
<p><small>সার্ভার ঘুমালে বা নতুন সংস্করণ চালু হলে এই সংখ্যা শূন্য হয়ে যায়।</small></p>
</body></html>"""
    return HTMLResponse(html)

@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    if os.environ.get("MAINTENANCE", "").lower() == "on":
        return {"reply": "অ্যাপে এখন রক্ষণাবেক্ষণের কাজ চলছে। একটু পরে আবার চেষ্টা করুন।"}
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"reply": "সার্ভার চলছে, কিন্তু API কী এখনো বসানো হয়নি।"}
    a = req.attachment
    if a and len(str(a.get("data", ""))) + len(str(a.get("text", ""))) > 6000000:
        return {"reply": "ফাইল বেশি বড়। ছোট ফাইল দিন।"}
    reset_if_new_day()
    ip = client_ip(request)
    try:
        limit = int(os.environ.get("DAILY_LIMIT", "30"))
    except ValueError:
        limit = 30
    used = STATS["ips"].get(ip, 0)
    if used >= limit:
        STATS["blocked"] += 1
        return {"reply": "আজকের ব্যবহারের সীমা শেষ হয়েছে। কাল আবার চেষ্টা করুন।"}
    STATS["ips"][ip] = used + 1
    STATS["total"] += 1
    STATS["all"] += 1
    msgs = []
    for m in req.messages[-20:]:
        if m.get("role") in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": str(m.get("content", ""))[:8000]})
    while msgs and msgs[0]["role"] != "user":
        msgs = msgs[1:]
    if not msgs:
        return {"reply": "মেসেজ পাওয়া যায়নি।"}
    if a and msgs[-1]["role"] == "user":
        blocks = []
        kind = a.get("type")
        if kind == "image":
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": a.get("media_type", "image/jpeg"), "data": a.get("data", "")}})
        elif kind == "pdf":
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": a.get("data", "")}})
        elif kind == "text":
            blocks.append({"type": "text", "text": "ফাইল (" + str(a.get("name", "")) + "):\n" + str(a.get("text", ""))[:20000]})
        blocks.append({"type": "text", "text": msgs[-1]["content"] or "এটা দেখো"})
        msgs = msgs[:-1] + [{"role": "user", "content": blocks}]
    system = "তুমি একজন সহায়ক। ব্যবহারকারী যে ভাষায় লেখে, সেই ভাষায় উত্তর দাও। " + STYLES.get(req.style, STYLES["short"])
    client = anthropic.Anthropic(api_key=key)

    def call(tools):
        kw = dict(model="claude-sonnet-5-5", max_tokens=1500, system=system, messages=msgs)
        if tools:
            kw["tools"] = tools
        return client.messages.create(**kw)

    try:
        if req.search:
            try:
                r = call([{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}])
            except Exception:
                r = call(None)
        else:
            r = call(None)
        return {"reply": text_of(r) or "উত্তর পাওয়া যায়নি।"}
    except Exception:
        return {"reply": "দুঃখিত, উত্তর আনতে সমস্যা হয়েছে। একটু পরে আবার চেষ্টা করুন।"}

def parse_json_block(text):
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no json")
    return json.loads(text[a:b + 1])

@app.post("/translate")
def translate(req: TranslateRequest, request: Request):
    name = LANG_NAMES.get(req.lang)
    if not name:
        return JSONResponse({"error": "unsupported"}, status_code=400)
    if req.lang in TR_CACHE:
        return {"map": TR_CACHE[req.lang]}
    if os.environ.get("MAINTENANCE", "").lower() == "on":
        return JSONResponse({"error": "maintenance"}, status_code=503)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return JSONResponse({"error": "nokey"}, status_code=503)
    d = str(date.today())
    if TR_USE["day"] != d:
        TR_USE["day"] = d
        TR_USE["ips"] = {}
    ip = client_ip(request)
    n = TR_USE["ips"].get(ip, 0)
    if n >= 8:
        return JSONResponse({"error": "limit"}, status_code=429)
    TR_USE["ips"][ip] = n + 1
    src = {}
    for k, v in list(req.strings.items())[:150]:
        src[str(k)[:40]] = str(v)[:600]
    prompt = (
        "Translate the values of this JSON object (mobile app interface texts) from English into "
        + name
        + ". Rules: keep every key exactly as it is; keep emoji and symbols (such as + > ☰) and numbers; "
        "keep brand and technical names unchanged (Google Play Billing, Chrome, PDF, MB); "
        "use short, natural wording suitable for app buttons and labels; add no explanations. "
        "Return ONLY the JSON object.\n\n" + json.dumps(src, ensure_ascii=False)
    )
    try:
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        data = parse_json_block(text_of(r))
        out = {k: str(data[k]) for k in src if k in data and isinstance(data[k], (str, int, float))}
        if len(out) < len(src) * 0.8:
            raise ValueError("incomplete")
        TR_CACHE[req.lang] = out
        return {"map": out}
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=502)

PHOTOS = {}
UP_USE = {"day": "", "ips": {}}

def is_image(data):
    return data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG"

@app.post("/upload")
async def upload(request: Request):
    if os.environ.get("MAINTENANCE", "").lower() == "on":
        return JSONResponse({"error": "maintenance"}, status_code=503)
    data = await request.body()
    if not data or len(data) > 15000000 or not is_image(data):
        return JSONResponse({"error": "bad"}, status_code=400)
    d = str(date.today())
    if UP_USE["day"] != d:
        UP_USE["day"] = d
        UP_USE["ips"] = {}
    ip = client_ip(request)
    n = UP_USE["ips"].get(ip, 0)
    if n >= 40:
        return JSONResponse({"error": "limit"}, status_code=429)
    UP_USE["ips"][ip] = n + 1
    now = time.time()
    for k in [k for k, v in PHOTOS.items() if now - v[0] > 180]:
        PHOTOS.pop(k, None)
    while len(PHOTOS) >= 6:
        PHOTOS.pop(min(PHOTOS, key=lambda k: PHOTOS[k][0]), None)
    tok = secrets.token_urlsafe(12)
    PHOTOS[tok] = (now, data)
    return PlainTextResponse("ph_" + tok)

@app.get("/photo/{tok}")
def photo(tok: str):
    item = PHOTOS.pop(tok, None)
    if not item:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    data = item[1]
    mt = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=data, media_type=mt, headers={"Cache-Control": "no-store"})

@app.post("/image")
def image(req: ImageRequest):
    return JSONResponse({"reply": "ছবি আঁকার সুবিধা এখনো চালু হয়নি।"}, status_code=501)
