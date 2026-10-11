import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    return {"status": "ok"}

@app.post("/chat")
def chat(req: ChatRequest):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"reply": "সার্ভার চলছে, কিন্তু API কী এখনো বসানো হয়নি।"}
    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1000,
        system="তুমি একজন সহায়ক। ব্যবহারকারী যে ভাষায় লেখে, সেই ভাষায় উত্তর দাও।",
        messages=req.messages,
    )
    return {"reply": response.content[0].text}

from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.post("/ask")
async def ask(request: Request):
    text = (await request.body()).decode("utf-8")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return PlainTextResponse("সার্ভার চলছে, কিন্তু API কী এখনো বসানো হয়নি।")
    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1000,
        system="তুমি একজন সহায়ক। ব্যবহারকারী যে ভাষায় লেখে, সেই ভাষায় উত্তর দাও।",
        messages=[{"role": "user", "content": text}],
    )
    return PlainTextResponse(response.content[0].text)
