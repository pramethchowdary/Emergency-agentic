import os
from google import genai
import dotenv
import requests
import json

class agents:
    def __init__(self):
        dotenv.load_dotenv()
        self.gemini_key = os.getenv("Gemini_API")
        self.client = genai.Client(api_key=self.gemini_key)    
    def extractor_node(self,text):
        systemPrompt =["you are working as first person of contact at emergency helpline. you need to return plain text no bold,ittalic text, you need to  extract the information from the transcribed call recordings. don't add hallucinate and return only the information that can be configured."]
        prompt = f""" here is the transcription of the call : {text}.
        the output should be in json format with following fields:
        {{
            "caller_name": "",
            "emergency_type": ""(faital, non-faital, crtical),
            "location": "",
            "number_of_people_involved": 0,
            "age_group": ""(child, adult, senior),
            "immediate_dangers": ""(fire, gas leak, structural damage, etc.),
            "medical_conditions": ""(if any known medical conditions are mentioned),
            "description": ""
        }}
        if observation is not found return N/A
        Please provide the extracted information in JSON format only.
        emergency type should be defined by you when you here the transcription.
        here is the example:
        {{
        "caller_name": "John Doe",
        "emergency_type": "critical",
        "location": "123 Main St, Springfield",
        "number_of_people_involved": 2, 
        "age_group": "adult",
        "immediate_dangers": "fire",
        "medical_conditions": "N/A",
        "description": "Caller reports a fire in their apartment building with two adults trapped inside."
        }}
        """
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=systemPrompt,
                max_output_tokens=300,
                temperature=0.2,
            )
        )
        return json.loads(response.text)
    
    def verifier_agent(self,parameters,information):
        systemPrompt =["you are working as second person of contact at emergency helpline. you need to verify the information extracted by first agent from the transcribed call recordings. you need to  verify the information from the transcribed call recordings. don't add hallucinate and return only the information that can be configured."]
        prompt = f""" here is the information extracted by first agent : {json.dumps(parameters)}.
        here is the transcription of the call : {information}.
        your task is to verify the information provided by first agent with respect to transcription provided.
        your task is to send a list[]
        first element is boolean value(True/False) that indecates wether information is correct and enough to dispatch emergency services.
        second element is if your first element is False then ask the necessary question to caller to get the missing information else return N/A.
        """
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=systemPrompt,
                max_output_tokens=300,
                temperature=0.2,
            )
        )
        return json.loads(response.text)

    pass