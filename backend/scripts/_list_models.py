import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google import genai

from config import load_settings

key = load_settings().gemini_api_keys[0]  # lists models visible to the first key
client = genai.Client(api_key=key)

print("Available models that support generateContent:")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(" ", m.name)
