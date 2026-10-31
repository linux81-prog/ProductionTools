"""FICTIONAL restaurant receipts with SIMULATED handwritten tips.

There is no handwriting font in the development environment. "Handwriting" here
is a sans-serif font drawn in blue ink, character by character, with random
rotation, size, slant and baseline wobble. Real handwriting varies far more,
which is why every handwritten amount is always flagged for a person to confirm.

Creates:
  receipts/04_harbor_light_diner_photo.jpg  card slip: tip and final total both written (in the demo envelope)
  tips/tip_no_final.jpg                      tip written, final total left blank
  tips/tip_mismatch.jpg                      tip and final total written, arithmetic off by $1.00
  tips/suggested_only.jpg                    suggested-gratuity lines only; nothing written
  tips/answer_keys.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_fixtures as mf  # noqa: E402

rng = np.random.default_rng(4242)
HAND_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
INK = (28, 48, 150)

BASE = [("HARBOR LIGHT DINER", "big"), ("19 Wharf Placeholder Rd", "c"), ("Morro Bay CA 93442", "c"),
        ("(555) 014-7711", "c"), ("", "c"), ("10/17/2026|7:48 PM", "lr"), ("Server: Dana   Table 12", "c"),
        ("-" * 34, "c"), ("CLAM CHOWDER x2|16.00", "lr"), ("FISH & CHIPS|18.50", "lr"), ("ICED TEA x2|7.50", "lr"),
        ("-" * 34, "c"), ("SUBTOTAL|42.00", "lr"), ("TAX|3.99", "lr"), ("TOTAL|45.99", "lr"), ("", "c"),
        ("MASTERCARD ****0000", "l"), ("", "c"), ("SUGGESTED GRATUITY", "c"), ("18% = 8.28", "c"), ("20% = 9.20", "c"),
        ("22% = 10.12", "c"), ("", "c"), ("TIP|___________", "lr"), ("", "c"), ("TOTAL|___________", "lr"), ("", "c"),
        ("X______________________", "c"), ("CUSTOMER COPY", "c")]
TIP_LINE = BASE.index(("TIP|___________", "lr"))
FINAL_LINE = BASE.index(("TOTAL|___________", "lr"))


def line_y(lines, idx, size=24, pad=36):
    lh = int(size * 1.45)
    return pad + sum(int(lh * (1.6 if s == "big" else 1)) for _, s in lines[:idx])


def handwrite(img: Image.Image, text: str, right_x: int, base_y: int, size: int = 34) -> None:
    """Draw text right-aligned at right_x, roughly on the baseline at base_y, in wobbly blue 'handwriting'."""
    glyphs = []
    for ch in text:
        s = int(size * rng.uniform(0.9, 1.15))
        font = ImageFont.truetype(HAND_FONT, s)
        w = int(font.getlength(ch)) + 10
        tile = Image.new("RGBA", (w + 10, s + 20), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((5, 5), ch, font=font, fill=INK + (255,), stroke_width=1, stroke_fill=INK + (255,))
        tile = tile.transform(tile.size, Image.AFFINE, (1, 0.25, -4, 0, 1, 0), resample=Image.BICUBIC)  # slant
        tile = tile.rotate(rng.uniform(-9, 9), resample=Image.BICUBIC, expand=True)
        glyphs.append((tile, w - 6 + int(rng.integers(-2, 3))))
    total_w = sum(adv for _, adv in glyphs)
    x = right_x - total_w
    for tile, adv in glyphs:
        y = base_y - tile.height + 12 + int(rng.integers(-4, 5))
        img.paste(tile, (x, y), tile)
        x += adv


def make(lines_written: dict[int, str], photo: bool) -> Image.Image:
    img = mf.render_thermal(BASE, paper=(252, 251, 246))
    for idx, txt in lines_written.items():
        handwrite(img, txt, right_x=img.width - 60, base_y=line_y(BASE, idx) + 24)
    if photo:
        return mf.phone_photo(mf.crumple(img, amp=2.5))
    a = np.asarray(img).astype("float32") + rng.normal(0, 3, (img.height, img.width, 3))
    return Image.fromarray(a.clip(0, 255).astype("uint8"))


def key(tip, final, total, status):
    return {"vendor": "Harbor Light Diner", "date": "2026-10-17", "subtotal": "42.00", "tax": "3.99",
            "printed_total": "45.99", "tip": tip, "final_total": final, "total": total, "payment": "Mastercard",
            "tip_status": status}


def main() -> dict:
    (mf.FIX / "tips").mkdir(parents=True, exist_ok=True)
    demo = make({TIP_LINE: "9.00", FINAL_LINE: "54.99"}, photo=True)
    demo.save(mf.FIX / "receipts" / "04_harbor_light_diner_photo.jpg", "JPEG", quality=86)
    cases = {
        "tip_no_final.jpg": ({TIP_LINE: "8.00"}, key("8.00", None, "53.99", "proposed")),
        "tip_mismatch.jpg": ({TIP_LINE: "9.00", FINAL_LINE: "55.99"}, key("9.00", "55.99", "55.99", "mismatch")),
        "suggested_only.jpg": ({}, key(None, None, "45.99", "none")),
    }
    keys = {}
    for name, (written, k) in cases.items():
        make(written, photo=False).save(mf.FIX / "tips" / name, "JPEG", quality=90)
        keys[name] = k
    (mf.FIX / "tips" / "answer_keys.json").write_text(json.dumps(keys, indent=2) + "\n")
    return {"04_harbor_light_diner_photo.jpg": key("9.00", "54.99", "54.99", "verified")}


if __name__ == "__main__":
    print(main())
