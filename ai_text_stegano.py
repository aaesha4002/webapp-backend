"""
ai_text_stegano.py — Bridge between the Flask webapp and the TransUNet
text-in-image steganography model in "Ai text in image/".

Exports:
    ai_text_hide(cover_bytes, text) -> PNG bytes
    ai_text_extract(stego_bytes)    -> str
"""
import sys
import io
import os
import tempfile
from pathlib import Path
from PIL import Image

# ── Path setup: add "Ai text in image" so its modules are importable ──────────
_AI_TEXT_DIR = Path(__file__).resolve().parent / "Ai text in image"
if str(_AI_TEXT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_TEXT_DIR))

# ── Model weight / config paths ────────────────────────────────────────────────
_ENCODER_PTH = _AI_TEXT_DIR / "weights_v3" / "encoder_best.pth"
_DECODER_PTH = _AI_TEXT_DIR / "weights_v3" / "decoder_best.pth"
_CONFIG_PTH  = _AI_TEXT_DIR / "weights_v3" / "config.json"

MAX_CHARS = 50  # 400 bits / 8 bits per byte


def _save_bytes_as_png(data: bytes) -> str:
    """Write image bytes to a temp PNG file; caller must delete it."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    img.save(tmp.name)
    return tmp.name


def ai_text_hide(cover_bytes: bytes, text: str) -> bytes:
    """Embed *text* into *cover* image using the TransUNet encoder."""
    from hide_text_v3 import hide

    cover_path = _save_bytes_as_png(cover_bytes)
    out_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    out_tmp.close()
    out_path = out_tmp.name

    try:
        hide(
            cover_path=cover_path,
            text=text,
            encoder_path=str(_ENCODER_PTH),
            config_path=str(_CONFIG_PTH),
            output_path=out_path,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (cover_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass


def ai_text_extract(stego_bytes: bytes) -> str:
    """Extract hidden text from *stego* image using the TransUNet decoder."""
    from extract_text_v3 import extract

    stego_path = _save_bytes_as_png(stego_bytes)
    try:
        text, _ = extract(
            stego_path=stego_path,
            decoder_path=str(_DECODER_PTH),
            config_path=str(_CONFIG_PTH),
        )
        return text
    finally:
        try:
            os.remove(stego_path)
        except OSError:
            pass
