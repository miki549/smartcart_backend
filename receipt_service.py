import os
import json
import time
from google import genai
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Az aktuálisan elérhető és támogatott modellek
AVAILABLE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.7-flash"
]

def analyze_receipt_image(image_path: str) -> dict:
    """
    Kép elemzése Gemini modellel.
    """
    if not GEMINI_API_KEY:
        raise ValueError("A GEMINI_API_KEY nincs beállítva a .env fájlban!")

    client = genai.Client(api_key=GEMINI_API_KEY)
    img = Image.open(image_path)

    prompt = """
    Elemezd ezt a magyar bolti blokkot / nyugtát!
    Kérlek, nyerd ki az alábbi adatokat szigorúan JSON formátumban:
    {
      "store_name": "A bolt neve (pl. Lidl, Aldi, Penny, Spar, Tesco, Auchan)",
      "total_amount": 1234.0,
      "date": "YYYY-MM-DD",
      "items": [
        {
          "product_name": "Egyszerűsített, tiszta terméknév (pl. Trappista sajt, Tej 1.5%, Csirkemell)",
          "quantity": 1.0,
          "unit_type": "db",
          "unit_price": 500.0,
          "total_price": 500.0
        }
      ]
    }
    Fontos: Csak az érvényes JSON szöveget add vissza, markdown kódblokkok (```json) nélkül!
    """

    last_error = None

    for model_name in AVAILABLE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[img, prompt],
            )
            
            clean_text = response.text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            return json.loads(clean_text.strip())

        except Exception as e:
            last_error = e
            # Ha elérhetetlen vagy túlterhelt, próbálja a következőt
            if any(err in str(e) for err in ["503", "404", "UNAVAILABLE", "NOT_FOUND", "high demand"]):
                time.sleep(1)
                continue
            raise e

    raise last_error