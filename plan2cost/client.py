"""Thin wrapper over an OpenAI-compatible chat endpoint, with image support."""
import base64
import mimetypes
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def get_client() -> OpenAI:
    return OpenAI(base_url=os.environ["P2C_BASE_URL"], api_key=os.environ["P2C_API_KEY"])


def model_name() -> str:
    return os.environ.get("P2C_MODEL", "meta-models/muse-spark-open-1026")


def image_part(path: str) -> dict:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
