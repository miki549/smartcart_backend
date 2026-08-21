import os
import json
import time
from typing import List, Optional
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

AVAILABLE_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.7-flash"
]

class ReceiptItem(BaseModel):
    product_name: str = Field(description="Egyszerűsített, tiszta terméknév (pl. Trappista sajt, Tej 1.5%, Csirkemell)")
    quantity: float = Field(description="Mennyiség")
    unit_type: str = Field(description="Mértékegység (pl. db, kg, l)")
    unit_price: float = Field(description="Egységár")
    total_price: float = Field(description="Tétel összesített ára")

class ReceiptData(BaseModel):
    is_receipt: bool = Field(
        description="True, ha a képen valódi bolti blokk/nyugta/számla látható, egyébként False."
    )
    store_name: Optional[str] = Field(
        default=None, 
        description="A bolt neve (pl. Lidl, Aldi, Penny, Spar, Tesco, Auchan), ha felismerhető"
    )
    total_amount: Optional[float] = Field(
        default=0.0, 
        description="A fizetett végösszeg"
    )
    date: Optional[str] = Field(
        default=None, 
        description="Dátum YYYY-MM-DD formátumban"
    )
    items: List[ReceiptItem] = Field(default_factory=list)

def analyze_receipt_image(image_path: str) -> dict:
    """
    Kép elemzése és blokk-érvényesség ellenőrzése Gemini modellel.
    """
    if not GEMINI_API_KEY:
        raise ValueError("A GEMINI_API_KEY nincs beállítva a .env fájlban!")

    client = genai.Client(api_key=GEMINI_API_KEY)
    img = Image.open(image_path)

    prompt = """
    Döntsd el a képről, hogy bolti blokk / nyugta / számla látható-e rajta.
    - Ha a kép NEM bolti blokk (pl. szelfi, általános tárgy, tájkép, nem számla jellegű dokumentum), állítsd az `is_receipt` értékét False-ra, és hagyd üresen az items listát!
    - Ha a kép valódi bolti blokk, állítsd az `is_receipt` értékét True-ra és nyerd ki a boltot, végösszeget, dátumot és a tételsorokat!
    """

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