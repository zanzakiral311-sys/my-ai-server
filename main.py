import os
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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

STYLES = {
    "short": "উত্তর সংক্ষিপ্ত ও সরাসরি রাখো।",
    "long": "উত্তর বিস্তারিত ও ধাপে ধাপে ব্যাখ্যা করে দাও।",
}

def text_of(resp):
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/privacy")
def privacy():
    return FileResponse("privacy.html")

@app.post("/chat")
def chat(req: ChatRequest):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"reply": "সার্ভার চলছে, কিন্তু API কী এখনো বসানো হয়নি।"}
    msgs = req.messages[-20:]
    while msgs and msgs[0].get("role") != "user":
        msgs = msgs[1:]
    a = req.attachment
    if a and msgs and msgs[-1].get("role") == "user":
        blocks = []
        kind = a.get("type")
        if kind == "image":
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": a.get("media_type", "image/jpeg"), "data": a.get("data", "")}})
        elif kind == "pdf":
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": a.get("data", "")}})
        elif kind == "text":
            blocks.append({"type": "text", "text": "ফাইল (" + str(a.get("name", "")) + "):\n" + str(a.get("text", ""))[:20000]})
        blocks.append({"type": "text", "text": msgs[-1].get("content") or "এটা দেখো"})
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

@app.post("/image")
def image(req: ImageRequest):
    return JSONResponse({"reply": "ছবি আঁকার সুবিধা এখনো চালু হয়নি।"}, status_code=501)
