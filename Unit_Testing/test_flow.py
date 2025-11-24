import asyncio
import json
import base64
import os
import librosa
import soundfile as sf
import websockets
import httpx
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
INPUT_FILE = "audio.wav"  # Put your downloaded file here
OUTPUT_FILE = "ai_response.raw"   # The AI's reply will be saved here
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Deepgram URL (Production Setup)
DEEPGRAM_STT_URL = "wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&channels=1&interim_results=true&endpointing=300"
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mulaw&sample_rate=8000"

# Gemini Setup
client = genai.Client(api_key=GEMINI_API_KEY)
SYSTEM_MESSAGE = "You are a helpful assistant. Respond briefly to the news report."

# --- 1. MOCK CLASS: SIMULATE TWILIO WEBSOCKET ---
class MockTwilioSocket:
    """
    This class pretends to be the FastAPI/Twilio WebSocket.
    Instead of sending audio to a phone, it saves it to a file.
    """
    def __init__(self):
        self.file_handle = open(OUTPUT_FILE, "wb")
        print(f"[MockTwilio] Saving AI audio to {OUTPUT_FILE}...")

    async def send_text(self, message: str):
        data = json.loads(message)
        event = data.get("event")

        if event == "media":
            # This is audio coming back from the AI
            payload = data["media"]["payload"]
            audio_chunk = base64.b64decode(payload)
            self.file_handle.write(audio_chunk)
            print(".", end="", flush=True) # visual indicator
        
        elif event == "mark":
            print(f"\n[MockTwilio] AI finished speaking a segment.")

    async def close(self):
        self.file_handle.close()
        print(f"\n[MockTwilio] Connection closed. File saved.")

# --- 2. HELPER FUNCTIONS (COPIED FROM YOUR MAIN.PY) ---
async def call_llm(user_text: str) -> str:
    print(f"\n[LLM] Thinking about: '{user_text}'")
    try:
        response = client.models.generate_content(
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
        return "I couldn't process that."

async def tts_to_audio(text: str) -> bytes:
    print(f"[TTS] Generating audio for: '{text.strip()}'")
    
    # Clean the text to remove accidental newlines
    clean_text = text.strip()
    
    # 1. Use the URL that already has the model params
    #    (model=aura-asteria-en, encoding=mulaw, etc.)
    # 2. ONLY send 'text' in the body. Do not send 'voice' or extra keys.
    body = {"text": clean_text}

    async with httpx.AsyncClient() as http_client:
        r = await http_client.post(
            DEEPGRAM_TTS_URL, 
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}, # Content-Type is auto-added by json=
            json=body
        )
        
        # This line is crucial! It will crash the script if Deepgram sends an error,
        # instead of saving the error message as a fake audio file.
        r.raise_for_status() 
        
        return r.content

# --- 3. MAIN TEST LOGIC ---
async def run_test():
    # A. PREPARE AUDIO (Convert wav to 8k mulaw on the fly)
    print(f"[Setup] Converting {INPUT_FILE} to 8000Hz Mulaw...")
    try:
        y, sr = librosa.load(INPUT_FILE, sr=8000, mono=True)
        # Convert float audio to 16-bit PCM then to Mulaw bytes would be complex manually.
        # EASIER TRICK: We will send raw bytes, but we need to match what Deepgram expects.
        # Since 'librosa' gives us float, let's use soundfile to write a temporary buffer 
        # that matches the format, or just verify the file exists and let logic handle it.
        
        # Actually, for the TEST, let's just send the raw wav and remove 'encoding=mulaw' 
        # from the URL strictly for the STT input part, BUT keep the output logic the same.
        # This allows us to test the PIPELINE without complex audio conversion code here.
        
        with open(INPUT_FILE, "rb") as f:
            audio_data = f.read()
            
    except FileNotFoundError:
        print("Error: Input file not found!")
        return

    # B. CONNECT TO DEEPGRAM
    # NOTE: We remove encoding=mulaw for the INPUT connection so it accepts your standard WAV file.
    TEST_STT_URL = "wss://api.deepgram.com/v1/listen?model=nova-2&smart_formatting=true&interim_results=true&endpointing=500"
    
    print(f"[Deepgram] Connecting...")
    async with websockets.connect(TEST_STT_URL, additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}) as dg_ws:
        print("[Deepgram] Connected.")
        
        # Initialize Mock Twilio
        mock_twilio = MockTwilioSocket()
        stream_sid = "TEST_STREAM_123" # Fake ID

        # C. START BACKGROUND TASK: SEND AUDIO
        async def send_audio_file():
            chunk_size = 4096
            print(f"[User] Speaking (Streaming {len(audio_data)} bytes)...")
            for i in range(0, len(audio_data), chunk_size):
                await dg_ws.send(audio_data[i:i+chunk_size])
                await asyncio.sleep(0.1) # Simulate talking speed
            
            # Send KeepAlive/Silence to allow processing to finish
            await asyncio.sleep(2) 
            
            try:
                # Try to close the stream gracefully
                await dg_ws.send(json.dumps([])) 
                print("\n[User] Sent close signal.")
            except websockets.exceptions.ConnectionClosed:
                # If Deepgram already closed it, that's fine!
                print("\n[User] Connection already closed by server. Done.")
        # D. START YOUR LOGIC (The function you wanted to test)
        # We paste the logic here, adapting 'websocket' to 'mock_twilio'
        async def deepgram_to_llm_and_tts_logic():
            try:
                async for message in dg_ws:
                    data = json.loads(message)
                    
                    if "channel" not in data: continue
                    
                    transcript = data["channel"]["alternatives"][0].get("transcript", "").strip()
                    is_final = data.get("is_final", False)

                    if not transcript: continue

                    # Log interim results
                    if not is_final:
                        print(f"\r[STT Interim] {transcript}", end="")
                    
                    # PROCESS FINAL RESULTS
                    if is_final:
                        print(f"\n[STT FINAL] {transcript}")

                        # 1. LLM
                        reply_text = await call_llm(transcript)
                        
                        # 2. TTS
                        audio_bytes = await tts_to_audio(reply_text)

                        # 3. Stream back (to Mock File)
                        chunk_size = 160
                        for i in range(0, len(audio_bytes), chunk_size):
                            chunk = audio_bytes[i : i + chunk_size]
                            payload = base64.b64encode(chunk).decode("utf-8")
                            
                            await mock_twilio.send_text(json.dumps({
                                "event": "media",
                                "media": {"payload": payload}
                            }))
                        
                        await mock_twilio.send_text(json.dumps({"event": "mark"}))

                    # Stop if we get metadata (stream over)
                    if data.get("type") == "Metadata":
                        break
            except Exception as e:
                print(f"Error in logic: {e}")

        # Run both
        await asyncio.gather(send_audio_file(), deepgram_to_llm_and_tts_logic())
        await mock_twilio.close()

if __name__ == "__main__":
    asyncio.run(run_test())