"""Original artwork for the independent demo catalogue.

Every image is drawn from scratch with Pillow primitives (flat, brick-style
illustrations of the fictional products described in ``data/demo/products.csv``).
No photographs, no Rebrickable/LEGO imagery and no third-party artwork are used
or traced. Output is deterministic, so re-running overwrites the files with
identical pixels::

    cd backend && ../.venv/bin/python -m brickwise.data.demo_artwork
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from .. import paths

SS = 2          # supersampling factor for anti-aliasing
SIZE = 512
W = SIZE * SS   # working canvas edge


def _s(v: float) -> int:
    return int(round(v * W / 100))  # coordinates are percent of the canvas


class Scene:
    def __init__(self, bg_top, bg_bottom):
        self.img = Image.new("RGB", (W, W), bg_top)
        d = ImageDraw.Draw(self.img)
        for y in range(W):  # vertical gradient
            t = y / (W - 1)
            c = tuple(int(bg_top[i] * (1 - t) + bg_bottom[i] * t) for i in range(3))
            d.line([(0, y), (W, y)], fill=c)
        self.d = d

    # ---- primitives (percent coordinates) ----
    def rect(self, x0, y0, x1, y1, fill, r=1.2, outline=None):
        self.d.rounded_rectangle([_s(x0), _s(y0), _s(x1), _s(y1)], radius=_s(r), fill=fill,
                                 outline=outline, width=SS * 2 if outline else 0)

    def ellipse(self, x0, y0, x1, y1, fill, outline=None):
        self.d.ellipse([_s(x0), _s(y0), _s(x1), _s(y1)], fill=fill, outline=outline,
                       width=SS * 2 if outline else 0)

    def poly(self, pts, fill):
        self.d.polygon([(_s(x), _s(y)) for x, y in pts], fill=fill)

    def line(self, pts, fill, width=1.0):
        self.d.line([(_s(x), _s(y)) for x, y in pts], fill=fill, width=max(1, _s(width)), joint="curve")

    def brick(self, x0, y0, x1, y1, color, studs=True, shade=True):
        """A brick: body, darker bottom edge, lighter top edge, and studs on top."""
        dark = tuple(max(0, int(c * 0.72)) for c in color)
        light = tuple(min(255, int(c * 1.12) + 6) for c in color)
        self.rect(x0, y0, x1, y1, color, r=0.8)
        if shade:
            self.rect(x0 + 0.3, y1 - 1.6, x1 - 0.3, y1 - 0.2, dark, r=0.5)
            self.rect(x0 + 0.3, y0 + 0.2, x1 - 0.3, y0 + 1.1, light, r=0.5)
        if studs:
            n = max(1, int((x1 - x0) // 4.2))
            pad = ((x1 - x0) - n * 3.0) / (n + 1)
            for i in range(n):
                sx = x0 + pad + i * (3.0 + pad)
                self.rect(sx, y0 - 1.5, sx + 3.0, y0 + 0.2, color, r=0.6)
                self.rect(sx + 0.3, y0 - 1.5, sx + 2.7, y0 - 1.0, light, r=0.4)

    def wheel(self, cx, cy, r, tire=(30, 30, 34), hub=(190, 190, 196)):
        self.ellipse(cx - r, cy - r, cx + r, cy + r, tire)
        self.ellipse(cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5, hub)
        self.ellipse(cx - r * 0.2, cy - r * 0.2, cx + r * 0.2, cy + r * 0.2, (90, 90, 96))

    def baseplate(self, y, color=(70, 150, 90), x0=4, x1=96):
        self.rect(x0, y, x1, y + 6, color, r=1.0)
        n = int((x1 - x0) // 6)
        for i in range(n):
            sx = x0 + 2 + i * 6
            self.rect(sx, y - 1.1, sx + 3.2, y + 0.3, color, r=0.6)

    def save(self, path: Path) -> None:
        out = self.img.resize((SIZE, SIZE), Image.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(path, "JPEG", quality=92, optimize=True)


# ---------------------------------------------------------------- scenes
def bw001():  # Ridgeback Rally Car
    s = Scene((255, 236, 205), (255, 205, 160))
    s.baseplate(74, (60, 60, 66))
    red, white = (210, 38, 38), (245, 245, 245)
    s.brick(14, 56, 86, 70, red)
    s.brick(28, 42, 66, 56, red)
    s.rect(32, 44, 46, 55, (150, 205, 235), r=0.8)
    s.rect(49, 44, 63, 55, (150, 205, 235), r=0.8)
    s.rect(14, 62, 86, 65, white, r=0.2)
    s.rect(10, 38, 24, 41, (30, 30, 34), r=0.5)  # spoiler wing
    s.rect(14, 40, 16, 56, (30, 30, 34), r=0.3)
    s.rect(21, 40, 23, 56, (30, 30, 34), r=0.3)
    s.rect(80, 64, 88, 68, (255, 220, 90), r=0.6)  # headlight
    s.wheel(30, 72, 7.5)
    s.wheel(70, 72, 7.5)
    return s


def bw002():  # Titan Track Excavator
    s = Scene((255, 244, 214), (240, 215, 160))
    s.baseplate(76, (150, 120, 80))
    yellow, dark = (250, 195, 20), (50, 50, 55)
    s.rect(12, 64, 62, 78, dark, r=4)  # track
    for i in range(7):
        s.ellipse(15 + i * 6.5, 66, 20 + i * 6.5, 76, (90, 90, 96))
    s.brick(18, 50, 60, 64, yellow)
    s.brick(20, 36, 40, 50, yellow)
    s.rect(23, 39, 37, 48, (150, 205, 235), r=0.8)
    s.line([(54, 52), (72, 30), (86, 46)], yellow, 4.2)  # boom + arm
    s.line([(54, 52), (72, 30), (86, 46)], (200, 150, 10), 1.0)
    s.poly([(82, 44), (96, 44), (92, 58), (80, 56)], (110, 110, 118))  # bucket
    s.ellipse(52, 49, 57, 54, (60, 60, 66))
    return s


def bw003():  # Skyline Commuter Jet
    s = Scene((150, 205, 245), (225, 242, 255))
    s.ellipse(8, 18, 30, 28, (255, 255, 255))
    s.ellipse(66, 70, 92, 80, (255, 255, 255))
    white, blue = (250, 250, 252), (30, 90, 190)
    s.rect(10, 42, 90, 58, white, r=8)  # fuselage
    s.poly([(10, 46), (2, 24), (18, 24), (24, 46)], blue)  # tail fin
    s.poly([(40, 52), (62, 52), (30, 84), (18, 84)], blue)  # wings
    s.poly([(40, 48), (62, 48), (36, 18), (26, 18)], (60, 125, 215))
    s.rect(12, 52, 88, 56, blue, r=0.4)
    for i in range(8):
        s.ellipse(26 + i * 5.6, 45, 29.4 + i * 5.6, 48.4, (140, 190, 230))
    s.poly([(80, 42), (92, 50), (80, 58)], (200, 210, 225))  # nose
    s.ellipse(45, 58, 55, 64, (110, 110, 118))  # engine
    return s


def bw004():  # Glasshouse Garden
    s = Scene((220, 240, 225), (180, 220, 190))
    s.baseplate(78, (80, 160, 90))
    s.rect(14, 38, 86, 78, (205, 235, 245), r=1.2)
    s.poly([(10, 40), (50, 14), (90, 40)], (190, 225, 238))
    for x in (14, 32, 50, 68, 86):
        s.line([(x, 38), (x, 78)], (120, 150, 160), 0.8)
    s.line([(14, 58), (86, 58)], (120, 150, 160), 0.8)
    s.line([(14, 38), (50, 14), (86, 38)], (120, 150, 160), 1.0)
    colors = [(235, 70, 110), (250, 190, 40), (180, 90, 200), (240, 110, 60)]
    for i in range(8):
        x = 20 + i * 8.2
        s.line([(x, 78), (x, 64 - (i % 3) * 4)], (50, 140, 60), 1.0)
        c = colors[i % 4]
        s.ellipse(x - 3.2, 58 - (i % 3) * 4, x + 3.2, 65 - (i % 3) * 4, c)
        s.ellipse(x - 1.2, 60 - (i % 3) * 4, x + 1.2, 62.4 - (i % 3) * 4, (255, 235, 130))
    s.rect(44, 62, 58, 78, (150, 105, 70), r=0.8)  # door
    return s


def bw005():  # Rescue Rotorcraft
    s = Scene((215, 235, 250), (250, 235, 220))
    orange, white = (245, 120, 20), (250, 250, 250)
    s.line([(14, 22), (86, 22)], (60, 60, 66), 1.4)  # rotor blade
    s.rect(47, 22, 53, 32, (80, 80, 88), r=0.5)
    s.rect(24, 32, 70, 58, orange, r=10)  # cabin
    s.rect(60, 36, 82, 42, orange, r=1.5)  # tail boom
    s.rect(78, 28, 84, 44, orange, r=1.5)
    s.rect(78, 26, 94, 29, (60, 60, 66), r=0.6)
    s.rect(30, 36, 50, 50, (150, 205, 235), r=3)  # windscreen
    s.rect(24, 52, 70, 56, white, r=0.5)
    s.rect(52, 38, 66, 50, white, r=1.0)  # red cross panel
    s.rect(58, 39.5, 60, 48.5, (220, 40, 40), r=0.3)
    s.rect(54.5, 43, 63.5, 45, (220, 40, 40), r=0.3)
    s.line([(30, 58), (30, 68)], (70, 70, 76), 1.0)
    s.line([(62, 58), (62, 68)], (70, 70, 76), 1.0)
    s.line([(18, 69), (74, 69)], (70, 70, 76), 1.6)
    return s


def bw006():  # Lunar Survey Rover
    s = Scene((14, 16, 40), (40, 44, 84))
    for (x, y) in [(10, 12), (28, 24), (46, 10), (70, 18), (88, 9), (80, 36), (18, 40), (58, 30)]:
        s.ellipse(x, y, x + 1.1, y + 1.1, (250, 250, 235))
    s.ellipse(-20, 72, 120, 200, (150, 150, 158))  # moon surface
    for (x, y, r) in [(16, 82, 4), (70, 88, 5), (46, 94, 3)]:
        s.ellipse(x - r, y - r * .5, x + r, y + r * .5, (120, 120, 128))
    white = (240, 240, 245)
    s.brick(24, 56, 70, 70, white)
    s.brick(30, 46, 52, 56, white)
    s.rect(33, 48, 49, 55, (90, 170, 230), r=0.8)
    s.poly([(62, 44), (92, 38), (92, 52), (62, 56)], (40, 90, 170))  # solar panel
    s.line([(66, 50), (88, 46)], (150, 190, 240), 0.5)
    s.line([(77, 40), (77, 52)], (150, 190, 240), 0.5)
    s.line([(26, 56), (20, 36)], (190, 190, 196), 0.9)  # dish mast
    s.ellipse(12, 28, 28, 40, (220, 220, 226))
    s.wheel(30, 74, 7)
    s.wheel(48, 74, 7)
    s.wheel(66, 74, 7)
    return s


def bw007():  # Moonstone Keep
    s = Scene((196, 170, 235), (250, 215, 235))
    s.baseplate(80, (96, 168, 96))
    grey, purple = (150, 152, 162), (120, 60, 180)
    s.brick(22, 46, 78, 80, grey, studs=False)
    for i in range(7):
        s.rect(22 + i * 8.4, 41, 22 + i * 8.4 + 5.2, 47, grey, r=0.5)  # battlements
    for tx in (10, 78):
        s.brick(tx, 38, tx + 14, 80, (170, 172, 182), studs=False)
        s.poly([(tx - 2, 38), (tx + 7, 12), (tx + 16, 38)], purple)
        s.line([(tx + 7, 12), (tx + 7, 3)], (80, 60, 40), 0.6)
        s.poly([(tx + 7, 3), (tx + 14, 5.5), (tx + 7, 8)], (230, 60, 90))
    s.poly([(40, 50), (50, 30), (60, 50)], purple)
    s.rect(44, 60, 56, 80, (90, 60, 40), r=5)  # gate
    for x in (30, 66):
        s.rect(x, 54, x + 4, 62, (255, 220, 120), r=1.0)
    for x, c in [(18, (240, 110, 150)), (84, (250, 190, 60)), (6, (250, 190, 60)), (94, (240, 110, 150))]:
        s.ellipse(x - 2, 76, x + 2, 80, c)
    return s


def bw008():  # Deepwater Explorer
    s = Scene((70, 165, 215), (10, 60, 110))
    for (x, y, r) in [(14, 20, 2), (22, 32, 1.4), (80, 18, 2.2), (88, 40, 1.2), (70, 70, 1.6)]:
        s.ellipse(x - r, y - r, x + r, y + r, (170, 220, 245))
    s.rect(0, 88, 100, 100, (60, 90, 100), r=0)
    teal = (20, 160, 160)
    s.ellipse(14, 40, 86, 74, teal)
    s.ellipse(20, 44, 80, 70, (30, 185, 185))
    s.ellipse(38, 24, 66, 52, (170, 225, 245))  # dome
    s.ellipse(41, 28, 52, 38, (225, 245, 255))
    s.ellipse(43, 36, 50, 46, (60, 90, 110))  # pilot
    s.ellipse(8, 52, 24, 62, (230, 230, 235))  # propeller hub
    s.line([(10, 50), (10, 64)], (230, 230, 235), 1.0)
    s.rect(26, 62, 74, 66, (14, 110, 115), r=0.5)
    for x in (36, 62):
        s.ellipse(x - 2.4, 52 - 2.4, x + 2.4, 52 + 2.4, (255, 235, 140))
    s.line([(50, 74), (50, 86)], (230, 230, 235), 0.9)  # landing legs
    s.line([(30, 86), (70, 86)], (230, 230, 235), 1.2)
    return s


def bw009():  # MetroLink Tram
    s = Scene((225, 230, 240), (190, 200, 215))
    s.rect(0, 74, 100, 100, (110, 112, 120), r=0)
    s.rect(0, 80, 100, 82, (200, 200, 210), r=0)
    s.line([(0, 76), (100, 76)], (60, 60, 66), 0.8)
    s.line([(36, 20), (40, 8)], (50, 50, 56), 0.9)  # pantograph
    s.line([(40, 8), (60, 8)], (50, 50, 56), 1.0)
    s.line([(0, 8), (100, 8)], (50, 50, 56), 0.4)
    s.line([(60, 8), (64, 20)], (50, 50, 56), 0.9)
    s.brick(8, 26, 92, 72, (250, 205, 30), studs=False)
    s.rect(8, 52, 92, 66, (140, 142, 150), r=0.5)
    for i in range(6):
        s.rect(12 + i * 13.4, 32, 22 + i * 13.4, 48, (150, 205, 235), r=1.4)
    s.rect(10, 28, 90, 31, (140, 142, 150), r=0.4)
    for x in (24, 76):
        s.wheel(x, 72, 5.2)
    s.rect(84, 36, 91, 48, (255, 245, 180), r=0.8)
    return s


def bw010():  # Redline Street Bike
    s = Scene((245, 245, 248), (214, 218, 226))
    s.rect(0, 78, 100, 100, (86, 88, 96), r=0)
    red = (205, 30, 36)
    s.wheel(24, 70, 14, hub=(215, 215, 220))
    s.wheel(76, 70, 14, hub=(215, 215, 220))
    s.line([(76, 70), (68, 44)], (170, 170, 178), 1.6)  # fork
    s.line([(68, 44), (64, 38)], (60, 60, 66), 2.0)  # handlebar
    s.rect(58, 33, 70, 38, (60, 60, 66), r=0.8)
    s.rect(30, 38, 62, 56, red, r=6)  # tank
    s.rect(18, 50, 42, 58, (50, 50, 56), r=2.0)  # seat
    s.rect(40, 54, 60, 70, (130, 132, 140), r=1.5)  # engine block
    for i in range(4):
        s.rect(43 + i * 4, 56, 44.6 + i * 4, 68, (200, 202, 208), r=0.2)
    s.line([(40, 66), (24, 70)], (90, 92, 100), 1.4)
    s.rect(6, 66, 22, 70, (190, 190, 198), r=1.0)  # exhaust
    s.ellipse(62, 44, 68, 50, (255, 240, 170))
    return s


def bw011():  # Coastal Research Vessel
    s = Scene((200, 232, 250), (160, 205, 235))
    s.rect(0, 66, 100, 100, (40, 120, 190), r=0)
    for i in range(6):
        s.line([(4 + i * 17, 74 + (i % 2) * 6), (12 + i * 17, 72 + (i % 2) * 6)], (140, 200, 240), 0.9)
    blue, white = (28, 80, 160), (250, 250, 252)
    s.poly([(8, 56), (92, 56), (82, 74), (16, 74)], blue)  # hull
    s.rect(10, 54, 90, 58, (230, 60, 50), r=0.4)
    s.brick(26, 42, 70, 56, white, studs=False)
    s.brick(34, 30, 58, 42, white, studs=False)
    s.rect(37, 33, 55, 39, (130, 190, 230), r=0.8)
    for i in range(5):
        s.rect(29 + i * 8, 46, 33.4 + i * 8, 51, (130, 190, 230), r=0.5)
    s.line([(42, 30), (42, 18)], (90, 90, 96), 0.8)  # mast
    s.line([(36, 22), (48, 22)], (90, 90, 96), 0.6)
    s.line([(74, 56), (74, 34), (86, 48)], (240, 190, 30), 1.4)  # crane
    s.line([(86, 48), (86, 56)], (60, 60, 66), 0.4)
    s.rect(12, 46, 22, 56, (240, 190, 30), r=0.8)  # container
    return s


def bw012():  # Jungle Stalker
    s = Scene((210, 240, 200), (150, 205, 150))
    for x, h in [(6, 52), (18, 36), (86, 48), (94, 30)]:
        s.line([(x, 80), (x, 80 - h)], (80, 140, 70), 2.0)
        s.ellipse(x - 8, 80 - h - 6, x + 8, 80 - h + 6, (60, 150, 80))
    s.rect(0, 80, 100, 100, (90, 70, 50), r=0)
    green, dark = (70, 165, 60), (40, 110, 45)
    s.poly([(10, 50), (30, 44), (30, 58), (4, 66)], dark)  # tail
    s.poly([(4, 66), (0, 70), (10, 62)], dark)
    s.rect(24, 40, 66, 66, green, r=9)  # body
    s.rect(60, 24, 80, 44, green, r=5)  # neck/head
    s.rect(70, 22, 94, 40, green, r=4)  # snout
    s.ellipse(76, 25, 81, 30, (255, 255, 255))
    s.ellipse(78, 26, 80, 29, (20, 20, 20))
    for i in range(4):
        s.poly([(78 + i * 3.6, 40), (80 + i * 3.6, 40), (79 + i * 3.6, 44)], (250, 250, 250))
    for x in (32, 50):
        s.rect(x, 62, x + 8, 80, dark, r=2.0)
        s.rect(x - 2, 78, x + 10, 82, dark, r=1.5)
    s.rect(64, 50, 76, 54, dark, r=1.0)  # arm
    for i in range(5):
        s.poly([(28 + i * 8, 40), (32 + i * 8, 40), (30 + i * 8, 34)], (240, 190, 40))
    return s


SCENES = {f"bw-{i:03d}.jpg": fn for i, fn in enumerate(
    [bw001, bw002, bw003, bw004, bw005, bw006, bw007, bw008, bw009, bw010, bw011, bw012], start=1)}


def generate(out_dir: Path | None = None) -> list[Path]:
    out_dir = Path(out_dir or paths.ROOT / "data" / "demo" / "images")
    written = []
    for name, fn in SCENES.items():
        p = out_dir / name
        fn().save(p)
        written.append(p)
    return written


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    for p in generate(out):
        print("wrote", p)


if __name__ == "__main__":
    main()
