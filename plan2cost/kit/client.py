"""Thin wrapper over an OpenAI-compatible chat endpoint (Meta Model API or Muse Spark Open), with image support and JSON replies."""
import base64
import json
import mimetypes
import os
import re

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
    """An OpenAI-compatible client for the active profile (or the one named). It always times out after two minutes and retries."""
    prefix = PROFILES[profile or active_profile()]
    # a call that has not answered in two minutes is a dead connection, not a slow model: give up and retry (the default is ten minutes, which hangs a whole floor)
    return OpenAI(base_url=os.environ[prefix + "BASE_URL"], api_key=os.environ[prefix + "API_KEY"], timeout=120.0, max_retries=2)


def model_name(profile: str | None = None) -> str:
    """The model id for the profile: `P2C_MODEL`, or `P2C_OPEN_MODEL` for Muse Spark Open, with defaults."""
    prefix = PROFILES[profile or active_profile()]
    return os.environ.get(prefix + "MODEL", "meta-models/muse-spark-open-1026" if prefix == "P2C_OPEN_" else "muse-spark-1.3")


def image_part(path: str) -> dict:
    """A picture file as the image part of a chat message (base64 data URL)."""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def parse_json(text: str) -> dict:
    """Models often wrap JSON in prose or fences; take the outermost object."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model reply")
    return json.loads(m.group(0))


def chat_json(content: list) -> dict:
    """One user turn (text and image parts) to the active model, reply parsed as a JSON object."""
    resp = get_client().chat.completions.create(model=model_name(), temperature=0, messages=[{"role": "user", "content": content}])
    return parse_json(resp.choices[0].message.content)
