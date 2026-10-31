"""Generate a harder FICTIONAL receipt set to measure OCR accuracy honestly.

The three demo receipts are fairly clean. This set uses the same kinds of
receipts with deliberately worse conditions: blur, sensor noise, heavy
crumpling, thermal fading, dim light and low resolution. Output goes to
fixtures/stress/ along with stress/answer_keys.json. Deterministic (fixed seed).

Run:  python tools/make_stress_set.py
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_fixtures as mf  # noqa: E402

OUT = mf.FIX / "stress"
VENDORS = ["GRIP & GAFF SUPPLY", "SUNSET LUMBER", "MAIN ST DELI", "STUDIO CITY OFFICE MART", "BLUE DOOR BAKERY",
           "VALLEY PAINT CENTER", "CORNER FUEL STOP", "HILLTOP HARDWARE", "LAKESIDE MARKET", "ACE PARTY RENTALS",
           "REDWOOD CRAFT SUPPLY", "NORTH END PHARMACY"]
ITEMS = ["PAINT ROLLER", "DROP CLOTH", "AA BATTERIES", "SANDWICH TRAY", "WATER CASE", "MARKERS 12PK", "LUMBER 2X4",
         "WOOD GLUE", "ICE BAG", "FOAM CORE", "SPRAY PAINT", "PAPER TOWELS", "CABLE TIES", "COFFEE BEANS"]

CONDITIONS = [  # (label, settings)
    ("clean photo", {}),
    ("motion blur", {"blur": 2.2}),
    ("heavy blur", {"blur": 3.2}),
    ("sensor noise", {"noise": 14}),
    ("heavy noise", {"noise": 24}),
    ("heavy crumple", {"crumple": 7.0}),
    ("faded thermal", {"fade": 0.55}),
    ("very faded thermal", {"fade": 0.72}),
    ("dim light", {"dim": 0.45}),
    ("low resolution", {"scale": 0.45}),
    ("very low resolution", {"scale": 0.32}),
    ("blur + noise + fade", {"blur": 1.8, "noise": 12, "fade": 0.45}),
]


def make(i: int, label: str, cfg: dict, rng: np.random.Generator):
    vendor = VENDORS[i]
    picks = rng.choice(len(ITEMS), size=3, replace=False)
    prices = [Decimal(int(rng.integers(150, 6000))) / 100 for _ in picks]
    sub = sum(prices)
    tax = (sub * Decimal("0.095")).quantize(Decimal("0.01"))
    total = sub + tax
    month, day = 10, int(rng.integers(1, 28))
    lines = [(vendor, "big"), (f"{int(rng.integers(100, 9999))} Sample Rd", "c"), ("(555) 01%d-%04d" % (i % 10, i * 37), "c"),
             ("", "c"), (f"{month:02d}/{day:02d}/2026|{int(rng.integers(7, 20))}:{int(rng.integers(10, 59))}", "lr"),
             ("-" * 34, "c")]
    lines += [(f"{ITEMS[p]}|{price:.2f}", "lr") for p, price in zip(picks, prices)]
    lines += [("-" * 34, "c"), (f"SUBTOTAL|{sub:.2f}", "lr"), (f"TAX|{tax:.2f}", "lr"), (f"TOTAL|${total:.2f}", "lr"),
              ("", "c"), (f"CASH|{(total + 5).quantize(Decimal('1')):.2f}", "lr"), ("THANK YOU", "c")]
    img = mf.render_thermal(lines)
    if "fade" in cfg:
        a = np.asarray(img).astype("float32")
        a = 255 - (255 - a) * (1 - cfg["fade"])
        img = Image.fromarray(a.clip(0, 255).astype("uint8"))
    img = mf.crumple(img, amp=cfg.get("crumple", 3.5))
    photo = mf.phone_photo(img)
    a = np.asarray(photo).astype("float32")
    if "dim" in cfg:
        a = a * cfg["dim"]
    if "blur" in cfg:
        a = cv2.GaussianBlur(a, (0, 0), cfg["blur"])
    if "noise" in cfg:
        a = a + rng.normal(0, cfg["noise"], a.shape)
    photo = Image.fromarray(a.clip(0, 255).astype("uint8"))
    if "scale" in cfg:
        photo = photo.resize((int(photo.width * cfg["scale"]), int(photo.height * cfg["scale"])), Image.LANCZOS)
    name = f"s{i + 1:02d}_{label.replace(' ', '_').replace('+', 'and')}.jpg"
    photo.save(OUT / name, "JPEG", quality=85)
    key = {"vendor": mf_title(vendor), "date": f"2026-{month:02d}-{day:02d}", "subtotal": f"{sub:.2f}",
           "tax": f"{tax:.2f}", "total": f"{total:.2f}", "payment": "Cash", "condition": label}
    return name, key


def mf_title(v: str) -> str:
    sys.path.insert(0, str(mf.ROOT / "src"))
    from productiontools.petty_cash.parse import tidy_vendor
    return tidy_vendor(v)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    keys = dict(make(i, label, cfg, rng) for i, (label, cfg) in enumerate(CONDITIONS))
    (OUT / "answer_keys.json").write_text(json.dumps(keys, indent=2) + "\n")
    print(f"{len(keys)} stress receipts written to {OUT}")


if __name__ == "__main__":
    main()
