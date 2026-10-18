import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.ai_extractor import _load_key
from google import genai

key = _load_key()
client = genai.Client(api_key=key)

print("Available models that support generateContent:")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(" ", m.name)
