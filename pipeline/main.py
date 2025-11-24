from fastapi import FastAPI
from pydantic import BaseModel
from agents import run_agent  # your agent pipeline

app = FastAPI()

class ChatInput(BaseModel):
    message: str

@app.post("/chat")
async def chat_with_agent(data: ChatInput):
    result = await run_agent(data.message)  # your agent pipeline
    return {"reply": result}
