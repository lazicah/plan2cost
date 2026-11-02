"""Muse Image on the Meta Model API: an image and a prompt in, an edited image out. Used to turn a screenshot of the 3D massing into a realistic illustration. It always uses the
Meta Model API (the partner hosts of Muse Spark Open do not serve it)."""
import base64

MODEL = "muse-image-1.0"


def edit_image(png: bytes, prompt: str, client=None) -> bytes:
    """One edit: returns the image bytes (webp by default). Content-safety blocks and busy backends surface as errors the caller shows."""
    if client is None:
        from plan2cost.kit.client import get_client

        client = get_client("meta")
    r = client.images.edit(model=MODEL, prompt=prompt, image=("view.png", png, "image/png"), n=1)
    return base64.b64decode(r.data[0].b64_json)
