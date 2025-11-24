import os
import json
import base64
import asyncio
import websockets
import re
from datetime import datetime
from websockets.asyncio.client import connect
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from dotenv import load_dotenv
import httpx
from google import genai
from google.genai import types

load_dotenv()

# --- CONFIGURATION ---
llm_key = os.getenv("GEMINI_API_KEY")
deepgram_key = os.getenv("DEEPGRAM_API_KEY")
SERVER_DOMAIN = "1a05c5954e2d.ngrok-free.app"

if not llm_key:
    raise ValueError("Missing GEMINI_API_KEY.")
if not deepgram_key:
    raise ValueError("Missing DEEPGRAM_API_KEY.")

# --------- LOGGING SETUP ---------
LOG_FILE = "conversation_logs.txt"

def log_to_file(role: str, text: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {role}: {text}\n")

def log_start_call():
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'-'*30}\nNEW CALL STARTED AT {datetime.now()}\n{'-'*30}\n")

# --------- LLM CONFIG ---------
client = genai.Client(api_key=llm_key)

SYSTEM_MESSAGE = (
    "You are an emergency helpline AI. "
    "You listen to the caller's words (transcriptions) and respond briefly, "
    "calmly and clearly with life-saving guidance. "
    "Avoid jokes, keep instructions step-by-step and simple. "
    "Do not use Markdown formatting (like **bold** or *italics*). "
    "Respond in plain text only."
)

# --------- DEEPGRAM CONFIG ---------
# endpointing=1000 means wait 1 second of silence before finalizing (prevents cutting off user)
DEEPGRAM_STT_URL = (
    "wss://api.deepgram.com/v1/listen?"
    "encoding=mulaw&sample_rate=8000&channels=1"
    "&smart_formatting=true&interim_results=true&endpointing=1000"
)

DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mulaw&sample_rate=8000"

app = FastAPI()

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Server is up and running"}

@app.api_route("/incoming_call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    response = VoiceResponse()
    response.say(
        "Welcome to the Emergency Helpline. "
        "You are connected to an AI assistant. "
        "Please describe your emergency after the beep and stay on the line."
    )
    connect_verb = Connect()
    connect_verb.stream(url=f"wss://{SERVER_DOMAIN}/audio_stream")
    response.append(connect_verb)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/audio_stream")
async def audio_stream_endpoint(websocket: WebSocket):
    print("Twilio client connected")
    await websocket.accept()
    log_start_call()
    stream_sid = None

    deepgram_headers = {"Authorization": f"Token {deepgram_key}"}
    
    try:
        dg_ws = await connect(
            DEEPGRAM_STT_URL,
            additional_headers=deepgram_headers,
        )
        print("Connected to Deepgram STT")
    except Exception as e:
        print(f"Failed to connect to Deepgram: {e}")
        await websocket.close()
        return

    async def twilio_to_deepgram():
        nonlocal stream_sid
        try:
            while True:
                msg = await websocket.receive_text()
                data = json.loads(msg)
                event = data.get("event")

                if event == "start":
                    stream_sid = data["start"]["streamSid"]
                    print(f"Stream started: {stream_sid}")
                elif event == "media":
                    payload = data["media"]["payload"]
                    audio_bytes = base64.b64decode(payload)
                    await dg_ws.send(audio_bytes)
                elif event == "stop":
                    print("Twilio sent stop event")
                    break
        except Exception as e:
            print(f"Twilio error: {e}")
        finally:
            try:
                await dg_ws.send(json.dumps([]))
            except:
                pass

    async def deepgram_to_llm_and_tts():
        try:
            async for message in dg_ws:
                try:
                    data = json.loads(message)
                except:
                    continue

                if "channel" not in data: continue
                
                transcript = data["channel"]["alternatives"][0].get("transcript", "").strip()
                is_final = data.get("is_final", False)

                if not transcript: continue

                if is_final:
                    print(f"[User] {transcript}")
                    log_to_file("User", transcript)

                    # 1. Call LLM (ASYNC NOW - Prevents Timeout)
                    reply_text = await call_llm(transcript)
                    
                    # 2. Post-process text to remove Markdown
                    clean_reply = re.sub(r'[*_#]', '', reply_text).strip()
                    
                    print(f"[AI] {clean_reply}")
                    log_to_file("AI", clean_reply)

                    # 3. TTS
                    try:
                        audio_bytes = await tts_to_audio(clean_reply)
                    except Exception as e:
                        print(f"TTS Error: {e}")
                        continue

                    # 4. Send Audio
                    if stream_sid:
                        chunk_size = 160
                        for i in range(0, len(audio_bytes), chunk_size):
                            chunk = audio_bytes[i : i + chunk_size]
                            payload = base64.b64encode(chunk).decode("utf-8")
                            await websocket.send_text(json.dumps({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload},
                            }))
                        
                        # Mark end so Twilio knows to listen again
                        await websocket.send_text(json.dumps({
                            "event": "mark",
                            "streamSid": stream_sid,
                            "mark": {"name": "end-tts"}
                        }))

        except Exception as e:
            print(f"Processing error: {e}")

    await asyncio.gather(twilio_to_deepgram(), deepgram_to_llm_and_tts())

# FIXED ASYNC FUNCTION
async def call_llm(user_text: str) -> str:
    try:
        # USE .aio FOR ASYNC (Non-blocking)
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_MESSAGE,
                max_output_tokens=150,
                temperature=0.2,
            )
        )
        return response.text
    except Exception as e:
        print(f"LLM Error: {e}")
        return "I am having trouble processing your request."

async def tts_to_audio(text: str) -> bytes:
    if not text: return b""
    async with httpx.AsyncClient(timeout=10.0) as client_http:
        r = await client_http.post(
            DEEPGRAM_TTS_URL, 
            headers={"Authorization": f"Token {deepgram_key}"},
            json={"text": text}
        )
        r.raise_for_status()
        return r.content