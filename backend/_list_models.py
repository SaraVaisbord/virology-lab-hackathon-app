import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
from google import genai

key = config.GEMINI_API_KEY
client = genai.Client(api_key=key)

print("Available models that support generateContent:")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(" ", m.name)
