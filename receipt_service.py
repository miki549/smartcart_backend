import os
import json
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def analyze_receipt_image(image_path: str) -> dict:
    """
    Kép elemzése a Gemini multimodális modellel.
    Visszaadja a blokk strukturált adatait JSON-ben.
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
      "total_amount": 1234.0,  (a blokk végösszege lebegőpontos számként)
      "date": "YYYY-MM-DD",    (vásárlás dátuma, ha olvasható)
      "items": [
        {
          "product_name": "Egyszerűsített, tiszta terméknév (pl. Trappista sajt, Tej 1.5%, Csirkemell)",
          "quantity": 1.0,     (mennyiség számként)
          "unit_type": "db",   (db, kg, l, csomag)
          "unit_price": 500.0, (egységár számként)
          "total_price": 500.0 (tétel teljes ára)
        }
      ]
    }
    Fontos: Csak az érvényes JSON szöveget add vissza, markdown kódblokkok (```json) nélkül!
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
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