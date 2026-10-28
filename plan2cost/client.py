"""Thin wrapper over an OpenAI-compatible chat endpoint, with image support."""
import base64
import mimetypes
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


PROFILES = {"meta": "P2C_", "open": "P2C_OPEN_"}  # Meta Model API (Muse Spark series) and Muse Spark Open on a partner host (Baseten)


def active_profile() -> str:
    """Which model host to use: set P2C_PROFILE=open to run everything on Muse Spark Open; the default is the Meta Model API."""
    p = os.environ.get("P2C_PROFILE", "meta")
    if p not in PROFILES:
        raise ValueError(f"P2C_PROFILE must be one of {sorted(PROFILES)}")
    return p


def get_client(profile: str | None = None) -> OpenAI:
    prefix = PROFILES[profile or active_profile()]
    return OpenAI(base_url=os.environ[prefix + "BASE_URL"], api_key=os.environ[prefix + "API_KEY"])


def model_name(profile: str | None = None) -> str:
    prefix = PROFILES[profile or active_profile()]
    return os.environ.get(prefix + "MODEL", "meta-models/muse-spark-open-1026" if prefix == "P2C_OPEN_" else "muse-spark-1.3")


def image_part(path: str) -> dict:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
