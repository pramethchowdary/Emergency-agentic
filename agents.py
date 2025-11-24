import os
import dotenv
class agents:
    def __init__(self):
        dotenv.load_dotenv()
        self.gemini_key = os.getenv("Gemini_API")
        self.deepgram_key = os.getenv("DEEPGRAM_API")
    def text_agent(self,audio):
        if not self.deepgram_key:
          raise ValueError("DEEPGRAM_API_KEY environment variable is not set")
        

        
    pass