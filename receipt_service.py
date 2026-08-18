import os
import json
import time
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AVAILABLE_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.7-flash"
]

class ReceiptItem(BaseModel):
    product_name: str = Field(description="Egyszerűsített, tiszta terméknév (pl. Trappista sajt, Tej 1.5%, Csirkemell)")
    quantity: float = Field(description="Mennyiség")
    unit_type: str = Field(description="Mértékegység (pl. db, kg)")
    unit_price: float = Field(description="Egységár")
    total_price: float = Field(description="Összesített ár az adott tételre")

class ReceiptData(BaseModel):
    store_name: str = Field(description="A bolt neve (pl. Lidl, Aldi, Penny, Spar, Tesco, Auchan)")
    total_amount: float = Field(description="A fizetett végösszeg")
    date: str = Field(description="Dátum YYYY-MM-DD formátumban")
    items: List[ReceiptItem]

def analyze_receipt_image(image_path: str) -> dict:
    """
    Kép elemzése Gemini modellel strukturált JSON kimenettel.
    """
    if not GEMINI_API_KEY:
        raise ValueError("A GEMINI_API_KEY nincs beállítva a .env fájlban!")

    client = genai.Client(api_key=GEMINI_API_KEY)
    img = Image.open(image_path)

    prompt = "Elemezd ezt a magyar bolti blokkot / nyugtát és nyerd ki az adatokat a megadott séma szerint!"

    last_error = None

    for model_name in AVAILABLE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[img, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ReceiptData,
                ),
            )
            return json.loads(response.text)

        except Exception as e:
            last_error = e
            if any(err in str(e) for err in ["503", "404", "UNAVAILABLE", "NOT_FOUND", "high demand"]):
                time.sleep(1)
                continue
            raise e

    raise last_error