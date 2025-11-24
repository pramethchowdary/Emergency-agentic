import streamlit as st
import requests
import json

st.set_page_config(page_title="Agentic AI Chat", layout="wide")

# -----------------------------------
# SESSION STATE
# -----------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🧠 Agentic AI Chat Interface")

# Backend endpoint (change according to your setup)
BACKEND_URL = "http://localhost:8000/chat"   # FastAPI route you will build


def send_message_to_backend(user_msg: str):
    """Send the user's message to your Agentic pipeline."""
    try:
        response = requests.post(
            BACKEND_URL,
            json={"message": user_msg},
            timeout=60
        )
        if response.status_code == 200:
            return response.json().get("reply", "No response from agent.")
        else:
            return f"⚠️ Backend error: {response.text}"
    except Exception as e:
        return f"⚠️ Request failed: {str(e)}"


# -----------------------------------
# DISPLAY CHAT MESSAGES
# -----------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -----------------------------------
# INPUT BOX
# -----------------------------------
if user_input := st.chat_input("Type your message..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Send to backend
    reply = send_message_to_backend(user_input)

    # Add bot reply
    st.session_state.messages.append({"role": "assistant", "content": reply})

    with st.chat_message("assistant"):
        st.markdown(reply)
