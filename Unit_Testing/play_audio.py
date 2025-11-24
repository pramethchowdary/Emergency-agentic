import soundfile as sf
import os

# 1. Read the raw mulaw file
try:
    data, samplerate = sf.read(
        "ai_response.raw", 
        channels=1, 
        samplerate=8000, 
        subtype='ULAW', 
        format='RAW'
    )
    
    # 2. Save it as a playable WAV
    sf.write("final_result.wav", data, samplerate)
    print("Success! Open 'final_result.wav' to hear your AI.")
    
    # Optional: Play immediately (Windows only)
    os.system("start final_result.wav")

except FileNotFoundError:
    print("Could not find 'ai_response.raw'. Did the test run?")