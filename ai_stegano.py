"""
ai_stegano.py — Bridge between the Flask webapp and the CNN-ViT steganography
model defined in the project root (inference.py / extract.py).

Exports:
    ai_hide(cover_bytes, secret_bytes) -> PNG bytes   (needs full checkpoint)
    ai_extract(container_bytes)        -> PNG bytes   (uses decoder_only.pth)
"""
import sys
import io
from pathlib import Path

import torch
from torchvision import transforms
from PIL import Image

# ── Path setup: add AI stego files folder so we can import inference.py / extract.py ──
_ROOT = Path(__file__).resolve().parent / "AI stego files"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from extract import CNNViTDecoder          # noqa: E402
from inference import SteganographySystem  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────
_DECODER_PTH    = _ROOT / "decoder_only.pth"
_FULL_MODEL_PTH = _ROOT / "best_model.pth"

_IMG_SIZE   = 512
_PATCH_SIZE = 16
_EMBED_DIM  = 768
_DEPTH      = 6
_NUM_HEADS  = 8

_transform = transforms.Compose([
    transforms.Resize((_IMG_SIZE, _IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
])

# ── Lazy-loaded decoder singleton ─────────────────────────────────────────────
_cached_decoder = None


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _tensor_to_png(t: torch.Tensor) -> bytes:
    """Convert a normalised (−1…1) model output tensor to PNG bytes."""
    t = torch.clamp((t + 1.0) / 2.0, 0.0, 1.0)
    img = transforms.ToPILImage()(t.squeeze(0).cpu())
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _load_image(data: bytes) -> torch.Tensor:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return _transform(img).unsqueeze(0)


def _load_decoder() -> CNNViTDecoder:
    global _cached_decoder
    if _cached_decoder is None:
        dev = _device()
        model = CNNViTDecoder(
            img_size=_IMG_SIZE,
            patch_size=_PATCH_SIZE,
            in_channels=3,
            embed_dim=_EMBED_DIM,
            depth=_DEPTH,
            num_heads=_NUM_HEADS,
        ).to(dev)
        state_dict = torch.load(_DECODER_PTH, map_location=dev)
        model.load_state_dict(state_dict)
        model.eval()
        _cached_decoder = model
    return _cached_decoder


# ── Public API ────────────────────────────────────────────────────────────────

def ai_hide(cover_bytes: bytes, secret_bytes: bytes) -> bytes:
    """Embed *secret* image inside *cover* image using the CNN-ViT encoder."""
    dev = _device()
    system = SteganographySystem(
        img_size=_IMG_SIZE,
        patch_size=_PATCH_SIZE,
        embed_dim=_EMBED_DIM,
        depth=_DEPTH,
        num_heads=_NUM_HEADS,
    ).to(dev)

    ckpt = torch.load(_FULL_MODEL_PTH, map_location=dev)
    if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
        sd = ckpt["model_state_dict"]
    else:
        sd = ckpt
    system.load_state_dict(sd)
    system.eval()

    cover  = _load_image(cover_bytes).to(dev)
    secret = _load_image(secret_bytes).to(dev)
    with torch.no_grad():
        container, _ = system(cover, secret)
    return _tensor_to_png(container)


def ai_extract(container_bytes: bytes) -> bytes:
    """Extract the hidden image from a container using the CNN-ViT decoder."""
    dev = _device()
    decoder = _load_decoder()
    stego = _load_image(container_bytes).to(dev)
    with torch.no_grad():
        revealed = decoder(stego)
    return _tensor_to_png(revealed)
