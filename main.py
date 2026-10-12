import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat")
def chat(req: ChatRequest):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"reply": "সার্ভার চলছে, কিন্তু API কী এখনো বসানো হয়নি।"}
    msgs = req.messages[-20:]
    while msgs and msgs[0].get("role") != "user":
        msgs = msgs[1:]
    try:
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=1000,
            system="তুমি একজন সহায়ক। ব্যবহারকারী যে ভাষায় লেখে, সেই ভাষায় উত্তর দাও।",
            messages=msgs,
        )
        return {"reply": r.content[0].text}
    except Exception:
        return {"reply": "দুঃখিত, উত্তর আনতে সমস্যা হয়েছে। একটু পরে আবার চেষ্টা করুন।"}
