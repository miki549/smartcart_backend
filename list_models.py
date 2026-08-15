import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

try:
    response = urllib.request.urlopen(url)
    data = json.loads(response.read())
    
    print("--- Elérhető Gemini modellek ---")
    for model in data.get('models', []):
        # Csak a neveket és a leírásokat írjuk ki
        print(f"- {model['name']} ({model.get('displayName', '')})")
except Exception as e:
    print(f"Hiba történt: {e}")