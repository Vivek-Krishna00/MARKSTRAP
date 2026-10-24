"""Draw a reel timeline (engine/reel.timeline) into an MP4 with MoviePy + ffmpeg (both open source).

No planning here: every time, position, colour and level comes from the timeline. Text layers are drawn once and
cached; each frame only moves, fades and stacks them. Run: python -m engine.compose timeline.json out.mp4
"""
import json
import re
import sys
import wave
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SR = 44100


def rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def lerp(a, b, p):
    return a + (b - a) * p


def back(x):
    """Ease-out with a small overshoot: stamps and slams land, then settle."""
    x = min(1.0, max(0.0, x)) - 1
    return 1 + 2.7 * x ** 3 + 1.7 * x ** 2


BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 + 1 / 32
ASCII = " .:-=+*#%@"


def field(kind: str, i: int, lt: float, w: int, h: int) -> np.ndarray:
    """A slowly moving 0..1 pattern per scene purpose; the brand's dither/ASCII look gives it character."""
    y, x = np.mgrid[0:h, 0:w]
    x, y = x / w, y / w  # square units: x 0..1, y 0..h/w
    if kind == "hook":  # shockwave rings out of the spotlight
        r = np.hypot(x - 0.5, (y - 0.38 * h / w))
        return np.clip(0.5 + 0.5 * np.sin(26 * r - 7 * lt) - 1.6 * r + 0.25, 0, 1)
    if kind == "problem":  # falling rain, one speed per column
        rng = np.random.default_rng(i)
        speed, phase = rng.uniform(0.25, 0.9, w), rng.uniform(0, 1, w)
        v = (y * w / h * 1.4 + lt * speed[None, :] + phase[None, :]) % 1.0
        return np.where(rng.uniform(0, 1, w)[None, :] < 0.55, v ** 6, 0.0)
    if kind == "demonstration":  # diagonal waves
        return 0.5 + 0.5 * np.sin(9 * (x + y) - 2.6 * lt) * np.sin(4 * (x - y) + 1.3 * lt)
    if kind == "proof":  # ripple from the top right corner
        r = np.hypot(x - 1.0, y)
        return np.clip(0.5 + 0.5 * np.sin(30 * r - 5 * lt) - 0.55 * r, 0, 1)
    if kind == "payoff":  # rotating sunburst behind the stamp
        cx, cy = 0.5, 0.33 * h / w
        a = np.arctan2(y - cy, x - cx)
        return np.clip((0.5 + 0.5 * np.sin(14 * a + 1.2 * lt)) * (1.25 - np.hypot(x - cx, y - cy)), 0, 1)
    pts = [(0.5 + 0.35 * np.sin(lt * 0.7 + k * 2.1 + i), (0.4 + 0.3 * np.cos(lt * 0.5 + k * 1.7)) * h / w)
           for k in range(3)]  # drifting blobs
    return np.clip(sum(0.045 / ((x - px) ** 2 + (y - py) ** 2 + 0.02) for px, py in pts) / 3, 0, 1)


NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
PRICE = re.compile(r"[₹$€£]\s?\d[\d,]*(?:\.\d+)?")


@lru_cache(maxsize=64)
def font(path: str, size: int, weight: str = "ExtraBold"):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_name(weight)
    except (OSError, ValueError, AttributeError):  # static fonts (user uploads) have no named weights
        pass
    return f


@lru_cache(maxsize=4096)
def has_glyph(path: str, ch: str) -> bool:
    """A character the font lacks renders as the same box as an unassigned code point."""
    if ch.isspace():
        return True

    def ink(c):
        im = Image.new("L", (64, 64))
        ImageDraw.Draw(im).text((8, 8), c, font=font(path, 40), fill=255)
        return im.tobytes()
    return ink(ch) != ink("\ue000")


def clean(text: str, path: str) -> str:
    return "".join(c for c in text if has_glyph(path, c)).strip()


def cover(img: Image.Image, W: int, H: int) -> Image.Image:
    s = max(W / img.width, H / img.height)
    img = img.resize((max(W, round(img.width * s)), max(H, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))


def wrap(text: str, f, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if cur and f.getlength(t) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur] if cur else lines


class Reel:
    def __init__(self, tl: dict):
        self.tl = tl
        self.W, self.H = tl["size"]
        cs = [rgb(c) for c in tl["colors"]] + [(8, 10, 14), (240, 241, 237), (145, 208, 255)]
        self.dark = min(cs[:3], key=lum)
        self.light = max(cs[:3], key=lum)
        self.accent = next((c for c in cs[:3] if c not in (self.dark, self.light)), cs[2])
        self.safe = tl["safe"]
        self.fpath = tl["font"]
        self.scenes = tl["scenes"]
        self.src, self.videos = {}, {}
        for s in self.scenes:
            if s["kind"] == "image" and s["path"]:
                k = max(s["zoom"])
                self.src[s["id"]] = cover(Image.open(s["path"]).convert("RGB"), int(self.W * k), int(self.H * k))
            elif s["kind"] == "video" and s["path"]:
                from moviepy import VideoFileClip
                self.videos[s["id"]] = VideoFileClip(s["path"], audio=False)
        self.logo = None
        if tl.get("logo"):
            lg = Image.open(tl["logo"]).convert("RGBA")
            lg.thumbnail((int(self.W * 0.42), int(self.H * 0.14)), Image.LANCZOS)
            self.logo = lg
        for s in self.scenes:
            s["text"] = clean(s["text"], self.fpath)
        words = [{**w, "w": clean(w["w"], self.fpath)} for w in tl["words"]]
        self.pages = self._pages([w for w in words if w["w"]], tl["caption"]["words"])
        self.cta = clean(tl.get("cta") or "", self.fpath)

    # ---------- backgrounds ----------

    @lru_cache(maxsize=32)
    def gradient(self, i: int) -> Image.Image:
        a, b = (self.dark, self.accent) if i % 2 == 0 else (self.dark, tuple(int(x * 0.55) for x in self.accent))
        y = np.linspace(0, 1, self.H)[:, None, None] ** 1.6
        g = (np.array(a)[None, None] * (1 - y) + np.array(b)[None, None] * y).repeat(self.W, 1)
        return Image.fromarray(g.astype(np.uint8))

    def motion(self, i: int, lt: float, dur: float) -> Image.Image:
        img = self.gradient(i).copy()
        d = ImageDraw.Draw(img, "RGBA")
        W, H = self.W, self.H
        r = W * 0.55
        cx, cy = W * (0.85 - 0.1 * lt / dur) + (i % 3) * W * 0.05, H * (0.2 + 0.04 * np.sin(lt * 1.3 + i))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*self.accent, 46))
        r2 = W * 0.32
        cx2, cy2 = W * (0.1 + 0.08 * lt / dur), H * (0.78 - 0.03 * np.cos(lt + i))
        d.ellipse((cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2), fill=(*self.light, 18))
        band = H * 0.035
        y0 = H * 0.66 + (lt / dur) * H * 0.04
        d.polygon([(0, y0), (W, y0 - H * 0.08), (W, y0 - H * 0.08 + band), (0, y0 + band)], fill=(*self.accent, 70))
        return img

    def still(self, s: dict, lt: float, dur: float) -> Image.Image:
        src = self.src[s["id"]]
        p = lt / dur
        z, k = lerp(*s["zoom"], p), max(s["zoom"])
        w, h = self.W * k / z, self.H * k / z
        cx = src.width / 2 + s["pan"][0] * p * (src.width - w)
        cy = src.height / 2 + s["pan"][1] * p * (src.height - h)
        x0, y0 = min(max(0.0, cx - w / 2), src.width - w), min(max(0.0, cy - h / 2), src.height - h)
        x0, y0 = max(0.0, x0), max(0.0, y0)  # float error at full zoom-out
        box = (x0, y0, min(src.width, x0 + w), min(src.height, y0 + h))
        return src.resize((self.W, self.H), Image.BILINEAR, box=box)

    def video(self, s: dict, lt: float) -> Image.Image:
        v = self.videos[s["id"]]
        return cover(Image.fromarray(v.get_frame(lt % max(v.duration - 0.05, 0.05))), self.W, self.H)

    # ---------- motion-graphics designs: one layout per scene purpose (the director picked the purpose) ----------

    @lru_cache(maxsize=32)
    def backdrop(self, i: int, purpose: str) -> Image.Image:
        W, H = self.W, self.H
        y, x = np.mgrid[0:H, 0:W]
        x, y = x / W, y / H
        d, a, l = (np.array(c, float) for c in (self.dark, self.accent, self.light))
        if purpose == "hook":  # spotlight glow behind the slam
            g = np.clip(1 - np.hypot(x - 0.5, (y - 0.4) * 0.8) / 0.62, 0, 1) ** 1.6 * 0.85
        elif purpose == "problem":  # dim, flat, a little claustrophobic
            g = 0.12 + 0.1 * y
            d = d * 0.7
        elif purpose == "demonstration":
            g = np.clip((x + y) / 2, 0, 1) ** 1.3 * 0.75
        elif purpose == "proof":  # dark with a quiet dot grid
            g = 0.18 * y + 0.35 * (((x * W) % (W / 18) < W / 200) & ((y * H) % (W / 18) < W / 200))
        elif purpose == "payoff":
            g = 0.95 - 0.55 * y
        else:
            g = (y ** 1.6) * (0.9 if i % 2 == 0 else 0.5)
        img = d[None, None] * (1 - g[..., None]) + a[None, None] * g[..., None]
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))

    @lru_cache(maxsize=1)
    def grain_layers(self) -> list:
        rng = np.random.default_rng(3)
        out = []
        for _ in range(3):
            n = rng.integers(0, 255, (self.H // 2, self.W // 2), dtype=np.uint8)
            layer = Image.merge("RGBA", [Image.fromarray(n)] * 3 + [Image.new("L", n.shape[::-1], 14)])
            out.append(layer.resize((self.W, self.H), Image.NEAREST))
        return out

    @lru_cache(maxsize=256)
    def text_layer(self, text: str, size: float, color: tuple, max_w: float = 0.84) -> Image.Image:
        f = font(self.fpath, int(self.W * size))
        lines = wrap(text, f, int(self.W * max_w)) or [""]
        lh = int(f.size * 1.12)
        img = Image.new("RGBA", (self.W, lh * len(lines) + int(f.size * 0.3)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for j, line in enumerate(lines):
            d.text((self.W / 2, j * lh), line, font=f, fill=color, anchor="ma")
        return img

    def design(self, s: dict, i: int, lt: float, dur: float, text: bool = True) -> Image.Image:
        img = self.backdrop(i, s["purpose"]).convert("RGBA")
        self.texture(img, s, i, lt)
        t, kind = s["text"], s["purpose"]
        if text and t:
            if kind == "hook":
                self.slam(img, t, lt)
            elif kind == "problem":
                self.typewriter(img, t, lt)
            elif kind == "proof" and NUM.search(t):
                self.counter(img, t, lt)
            elif kind == "payoff" and PRICE.search(t):
                self.price_tag(img, t, lt)
            elif kind == "demonstration":
                self.card(img, t, lt, dur)
            else:
                layer = self.title_layer(t, True)
                a = ease(lt / 0.35)
                self.paste(img, layer, int(self.H * 0.36 - layer.height / 2 + (1 - a) * self.H * 0.03), a)
        img.alpha_composite(self.grain_layers()[int(lt * 12) % 3])
        return img

    @lru_cache(maxsize=4)
    def ascii_atlas(self, cell: int) -> np.ndarray:
        f = font(self.fpath, int(cell * 1.1), "Bold")
        out = np.zeros((len(ASCII), cell, cell), np.uint8)
        for k, ch in enumerate(ASCII):
            im = Image.new("L", (cell, cell))
            ImageDraw.Draw(im).text((cell / 2, cell / 2), ch, font=f, fill=255, anchor="mm")
            out[k] = np.asarray(im)
        return out

    def texture(self, img, s: dict, i: int, lt: float):
        """Moving dither (or ASCII) layer between the backdrop and the text."""
        tx = self.tl.get("texture") or {}
        kind = s["purpose"]
        if kind in ("problem", "cta") and tx.get("ascii"):
            cell = max(8, self.W // 34)
            cols, rows = self.W // cell + 1, self.H // cell + 1
            idx = np.clip((field(kind, i, lt, cols, rows) * len(ASCII)).astype(int), 0, len(ASCII) - 1)
            a = self.ascii_atlas(cell)[idx].transpose(0, 2, 1, 3).reshape(rows * cell, cols * cell)[:self.H, :self.W]
            col = self.light
            alpha = (a.astype(np.uint16) * tx["ascii"] // 255).astype(np.uint8)
        elif tx.get("dither"):
            px = max(2, self.W // 135)  # chunky dither pixels
            w, h = self.W // px + 1, self.H // px + 1
            f = field(kind, i, lt, w, h)
            mask = f > np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]
            alpha = np.kron(mask.astype(np.uint8) * tx["dither"], np.ones((px, px), np.uint8))[:self.H, :self.W]
            col = self.accent if kind != "payoff" else self.dark
        else:
            return
        layer = np.empty((self.H, self.W, 4), np.uint8)
        layer[..., :3] = col
        layer[..., 3] = alpha
        img.alpha_composite(Image.fromarray(layer, "RGBA"))

    @lru_cache(maxsize=32)
    def slam_layout(self, text: str):
        f = font(self.fpath, int(self.W * 0.13))
        lines = wrap(text.upper(), f, int(self.W * 0.86))
        lh, sp = int(f.size * 1.08), f.getlength(" ")
        top = self.H * 0.38 - lh * len(lines) / 2
        out, k = [], 0
        for li, line in enumerate(lines):
            ws = line.split()
            x = (self.W - f.getlength(line)) / 2
            for w in ws:
                col = self.accent if (k % 3 == 2 or w is ws[-1] and li == len(lines) - 1) else self.light
                im = Image.new("RGBA", (int(f.getlength(w)) + 4, int(f.size * 1.25)), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((2, 0), w, font=f, fill=col)
                out.append((im, x + im.width / 2, top + li * lh + im.height / 2))
                x += f.getlength(w) + sp
                k += 1
        return out

    def slam(self, img, text, lt):
        words = self.slam_layout(text)
        last = max(0.0, min(len(words) - 1, (lt - 0.05) / 0.13))
        shake = np.sin(lt * 70) * self.W * 0.008 * np.exp(-((lt - 0.05) % 0.13) * 18) if lt < 0.05 + 0.13 * len(words) else 0
        for k, (im, cx, cy) in enumerate(words):
            p = (lt - 0.05 - k * 0.13) / 0.16
            if p <= 0:
                continue
            sc = 1 + 0.9 * (1 - ease(p))
            w = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))))
            if p < 1:
                w.putalpha(w.getchannel("A").point(lambda v: int(v * min(1.0, p * 2))))
            img.alpha_composite(w, (int(cx - w.width / 2 + shake), int(cy - w.height / 2)))
        return last

    def typewriter(self, img, text, lt):
        n = int(len(text) * min(1.0, max(0.0, (lt - 0.1) / max(0.6, 0.035 * len(text)))))
        f = font(self.fpath, int(self.W * 0.095))
        lines = wrap(text[:n], f, int(self.W * 0.84)) or [""]
        lh = int(f.size * 1.15)
        y0 = self.H * 0.38 - lh * len(lines) / 2
        d = ImageDraw.Draw(img)
        for j, line in enumerate(lines):
            d.text((self.W * 0.08, y0 + j * lh), line, font=f, fill=self.light)
        if int(lt * 2.4) % 2 == 0 or n < len(text):  # blinking cursor
            x = self.W * 0.08 + f.getlength(lines[-1]) + f.size * 0.08
            y = y0 + (len(lines) - 1) * lh
            d.rectangle((x, y + f.size * 0.12, x + f.size * 0.42, y + f.size * 1.05), fill=self.accent)

    def counter(self, img, text, lt):
        tok = NUM.search(text).group(0)
        target = float(tok.replace(",", ""))
        dec = len(tok.split(".")[1]) if "." in tok else 0
        v = target * ease((lt - 0.1) / 0.9)
        shown = f"{v:,.{dec}f}" if "," in tok else f"{v:.{dec}f}"
        big = self.text_layer(shown, 0.24, self.accent)
        self.paste(img, big, int(self.H * 0.25), ease(lt / 0.2))
        y = self.H * 0.25 + big.height
        if target <= 5 and dec:  # a rating: five stars fill as the number climbs
            r, cx0 = self.W * 0.05, self.W / 2 - self.W * 0.24
            d = ImageDraw.Draw(img, "RGBA")
            for k in range(5):
                cx, cy = cx0 + k * self.W * 0.12, y + r * 1.4
                pts = [(cx + (r if j % 2 == 0 else r * 0.45) * np.sin(j * np.pi / 5),
                        cy - (r if j % 2 == 0 else r * 0.45) * np.cos(j * np.pi / 5)) for j in range(10)]
                fill = min(1.0, max(0.0, v - k))
                d.polygon(pts, fill=(*self.accent, int(40 + 215 * fill)), outline=(*self.light, 120))
            y += r * 3.2
        rest = self.text_layer(text, 0.06, self.light)
        self.paste(img, rest, int(y + self.H * 0.02), ease((lt - 0.4) / 0.4))

    @lru_cache(maxsize=8)
    def tag_layer(self, tok: str) -> Image.Image:
        R = int(self.W * 0.24)
        im = Image.new("RGBA", (2 * R + 8, 2 * R + 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((4, 4, 2 * R + 4, 2 * R + 4), fill=self.light)
        d.ellipse((4 + R * 0.08, 4 + R * 0.08, 2 * R + 4 - R * 0.08, 2 * R + 4 - R * 0.08), outline=self.dark,
                  width=max(2, int(R * 0.02)))
        f = font(self.fpath, int(R * 0.62 if len(tok) <= 4 else R * 0.5))
        d.text((R + 4, R + 4), tok, font=f, fill=self.dark, anchor="mm")
        return im.rotate(-9, resample=Image.BICUBIC, expand=True)

    def price_tag(self, img, text, lt):
        tok = PRICE.search(text).group(0).replace(" ", "")
        tag = self.tag_layer(tok)
        p = (lt - 0.1) / 0.35
        if p > 0:
            sc = lerp(1.7, 1.0, back(p))
            t = tag.resize((max(1, int(tag.width * sc)), max(1, int(tag.height * sc))))
            if p < 1:
                t.putalpha(t.getchannel("A").point(lambda v: int(v * min(1.0, p * 3))))
            img.alpha_composite(t, (int(self.W / 2 - t.width / 2), int(self.H * 0.33 - t.height / 2)))
        rest = text.replace(PRICE.search(text).group(0), "").strip(" ·-,")
        if rest:
            self.paste(img, self.text_layer(rest, 0.075, self.light), int(self.H * 0.33 + tag.height * 0.55),
                       ease((lt - 0.45) / 0.35))

    def card(self, img, text, lt, dur):
        W, H = self.W, self.H
        cw, ch = W * 0.8, H * 0.27
        y = lerp(H * 1.02, H * 0.25, back(lt / 0.55))
        x0 = (W - cw) / 2
        d = ImageDraw.Draw(img, "RGBA")
        d.rounded_rectangle((x0 + W * 0.015, y + W * 0.025, x0 + cw + W * 0.015, y + ch + W * 0.025),
                            radius=int(W * 0.05), fill=(0, 0, 0, 70))  # shadow
        d.rounded_rectangle((x0, y, x0 + cw, y + ch), radius=int(W * 0.05), fill=self.light)
        inner = self.text_layer(text, 0.075, self.dark, 0.7)
        img.alpha_composite(inner, (0, int(y + ch * 0.38 - inner.height / 2)))
        bx, by, bw, bh = x0 + cw * 0.1, y + ch * 0.78, cw * 0.8, ch * 0.06
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=int(bh / 2), fill=(*self.dark, 40))
        d.rounded_rectangle((bx, by, bx + max(bh, bw * ease(lt / max(0.5, dur * 0.85))), by + bh),
                            radius=int(bh / 2), fill=self.accent)

    # ---------- text layers (cached) ----------

    @lru_cache(maxsize=128)
    def title_layer(self, text: str, big: bool) -> Image.Image:
        W = self.W
        f = font(self.fpath, int(W * (0.105 if big else 0.07)))
        lines = wrap(text, f, W - 2 * self.safe["side"])
        lh = int(f.size * 1.12)
        pad = int(W * 0.03)
        img = Image.new("RGBA", (W, lh * len(lines) + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if not big:  # over footage: a soft dark plate keeps it readable
            wmax = max(f.getlength(x) for x in lines)
            d.rounded_rectangle(((W - wmax) / 2 - pad, 0, (W + wmax) / 2 + pad, img.height), radius=pad,
                                fill=(*self.dark, 170))
        for j, line in enumerate(lines):
            d.text((W / 2, pad + j * lh), line, font=f, fill=self.light, anchor="ma",
                   stroke_width=0 if not big else int(W * 0.004), stroke_fill=self.dark)
        return img

    def _pages(self, words, n):
        pages, cur = [], []
        for w in words:
            if cur and (len(cur) >= n or w["t0"] - cur[-1]["t1"] > 0.25 or
                        (len(cur) >= 2 and cur[-1]["w"][-1:] in ".!?")):
                pages.append(cur)
                cur = []
            cur.append(w)
        return pages + [cur] if cur else pages

    @lru_cache(maxsize=512)
    def caption_layer(self, pi: int, active: int) -> Image.Image:
        cap, W = self.tl["caption"], self.W
        colors = [rgb(c) for c in cap.get("colors") or ["#FFFFFF"]] + [self.accent]
        f = font(self.fpath, int(W * 0.068))
        words = [w["w"] for w in self.pages[pi]]
        max_w = min(W - 2 * self.safe["side"], f.getlength("M" * cap["max_chars"]) * 0.62)
        lines, cur = [], []
        for j, w in enumerate(words):
            if cur and f.getlength(" ".join(words[k] for k in cur + [j])) > max_w:
                lines.append(cur)
                cur = []
            cur.append(j)
        lines.append(cur)
        lh, sp, pad = int(f.size * 1.25), f.getlength(" "), int(W * 0.012)
        img = Image.new("RGBA", (W, lh * len(lines) + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, line in enumerate(lines):
            widths = [f.getlength(words[j]) for j in line]
            x = (W - sum(widths) - sp * (len(line) - 1)) / 2
            y = pad + li * lh
            for j, wd in zip(line, widths):
                if j == active:
                    _, top, _, bottom = d.textbbox((x, y), words[j], font=f)
                    d.rounded_rectangle((x - pad, top - pad, x + wd + pad, bottom + pad), radius=pad, fill=colors[1])
                    fill = self.dark if lum(colors[1]) > 128 else (255, 255, 255)
                    d.text((x, y), words[j], font=f, fill=fill)
                else:
                    d.text((x, y), words[j], font=f, fill=colors[0], stroke_width=int(W * 0.005), stroke_fill=(0, 0, 0))
                x += wd + sp
        return img

    # ---------- frame ----------

    def scene_frame(self, i: int, lt: float) -> Image.Image:
        s = self.scenes[i]
        dur = s["end"] - s["start"]
        lt = min(max(lt, 0), dur)
        if s["id"] in self.src:
            img = self.still(s, lt, dur)
        elif s["id"] in self.videos:
            img = self.video(s, lt)
        else:
            img = self.design(s, i, lt, dur, text=i != len(self.scenes) - 1)
        img = img.convert("RGBA")
        last = i == len(self.scenes) - 1
        if last:
            return self.end_card(img, s, lt)
        motion = s["id"] not in self.src and s["id"] not in self.videos
        if s["text"] and not motion:  # motion scenes draw their own text in design()
            layer = self.title_layer(s["text"], False)
            a = ease(lt / 0.35)
            y = (self.H * 0.36 if motion else self.safe["top"] + self.H * 0.02) + (1 - a) * self.H * 0.03
            self.paste(img, layer, int(y - (layer.height / 2 if motion else 0)), a)
        return img

    def end_card(self, img: Image.Image, s: dict, lt: float) -> Image.Image:
        W, H = self.W, self.H
        a = ease(lt / 0.4)
        img = Image.alpha_composite(img, Image.new("RGBA", img.size, (*self.dark, int(150 * a))))
        y = H * 0.30
        if self.logo:
            sc = lerp(0.8, 1.0, ease(lt / 0.5))
            lg = self.logo.resize((max(1, int(self.logo.width * sc)), max(1, int(self.logo.height * sc))))
            self.paste(img, lg, int(y - lg.height / 2), a, x=int((W - lg.width) / 2))
            y += self.logo.height * 0.7 + H * 0.03
        if s["text"]:
            t = self.title_layer(s["text"], True)
            self.paste(img, t, int(y), ease((lt - 0.15) / 0.4))
            y += t.height + H * 0.025
        if self.cta:
            btn = self.cta_layer(self.cta)
            pulse = 1 + 0.035 * max(0.0, np.sin(2 * np.pi * 1.1 * (lt - 0.7))) if lt > 0.7 else 1
            if pulse != 1:  # the button breathes once it has landed
                bw, bh = int(btn.width * pulse), int(btn.height * pulse)
                cut = (bw - W) // 2  # the layer is frame-wide: scale it, then crop back to the frame
                btn = btn.resize((bw, bh)).crop((cut, 0, cut + W, bh))
                self.paste(img, btn, int(y - (bh - self.cta_layer(self.cta).height) / 2), 1)
            else:
                self.paste(img, btn, int(y + (1 - ease((lt - 0.3) / 0.4)) * H * 0.02), ease((lt - 0.3) / 0.4))
        return img

    @lru_cache(maxsize=4)
    def cta_layer(self, text: str) -> Image.Image:
        W = self.W
        f = font(self.fpath, int(W * 0.06))
        tw, pad = f.getlength(text), int(W * 0.045)
        img = Image.new("RGBA", (W, int(f.size * 1.3 + pad * 1.4)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(((W - tw) / 2 - pad, 0, (W + tw) / 2 + pad, img.height - 1), radius=img.height // 2,
                            fill=self.accent)
        d.text((W / 2, img.height / 2), text, font=f, fill=self.dark if lum(self.accent) > 128 else (255, 255, 255),
               anchor="mm")
        return img

    @staticmethod
    def paste(img, layer, y, alpha, x=0):
        if alpha <= 0:
            return
        if alpha < 1:
            layer = layer.copy()
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
        img.alpha_composite(layer, (x, max(0, y)))

    def frame(self, t: float) -> np.ndarray:
        i = next((j for j, s in enumerate(self.scenes) if t < s["end"]), len(self.scenes) - 1)
        s = self.scenes[i]
        img = self.scene_frame(i, t - s["start"])
        T = min(self.tl["transition_s"], (s["end"] - s["start"]) * 0.4)
        if s["transition"] != "cut" and i + 1 < len(self.scenes) and t > s["end"] - T:
            p = ease((t - (s["end"] - T)) / T)
            nxt = self.scene_frame(i + 1, 0)
            if s["transition"] == "crossfade":
                img = Image.blend(img, nxt, p)
            else:  # slide: up; whip: sideways
                off = (int(self.H * (1 - p)), 0) if s["transition"] == "slide" else (0, int(self.W * (1 - p)))
                img.alpha_composite(nxt, (off[1], off[0]))
        self.captions(img, t)
        return np.asarray(img.convert("RGB"))

    def captions(self, img, t):
        for pi, page in enumerate(self.pages):
            nxt = self.pages[pi + 1][0]["t0"] if pi + 1 < len(self.pages) else 1e9
            if page[0]["t0"] <= t < min(page[-1]["t1"] + 0.2, nxt):
                active = max((j for j, w in enumerate(page) if w["t0"] <= t), default=0)
                layer = self.caption_layer(pi, active)
                pos = (self.tl["caption"].get("position") or "bottom").lower()
                y = (self.H * 0.55 if "center" in pos or "middle" in pos else
                     self.safe["top"] + self.H * 0.12 if "top" in pos else self.H - self.safe["bottom"] - layer.height)
                pop = ease((t - page[0]["t0"]) / 0.12)
                self.paste(img, layer, int(y + (1 - pop) * self.H * 0.012), pop)
                return


# ---------- audio ----------

def load_audio(path: str) -> np.ndarray:
    if path.lower().endswith(".wav"):
        try:
            with wave.open(path) as w:
                raw = np.frombuffer(w.readframes(w.getnframes()), dtype={1: np.int8, 2: "<i2", 4: "<i4"}[w.getsampwidth()])
                x = raw.astype(float).reshape(-1, w.getnchannels()).mean(1) / float(2 ** (8 * w.getsampwidth() - 1))
                sr = w.getframerate()
            return np.interp(np.arange(int(len(x) * SR / sr)) * sr / SR, np.arange(len(x)), x) if sr != SR else x
        except wave.Error:  # compressed WAV: let ffmpeg decode it
            pass
    from moviepy import AudioFileClip
    with AudioFileClip(path) as a:
        x = a.to_soundarray(fps=SR)
    return x.mean(1) if x.ndim == 2 else x


def mix(tl: dict) -> np.ndarray:
    D = tl["duration"]
    n = int(D * SR)
    out = np.zeros(n)
    m = tl["music"]
    if m.get("path"):
        x = load_audio(m["path"])
        if len(x):
            x = np.tile(x, n // len(x) + 1)[:n]
            g = np.full(n, m["volume"])
            for v in tl["vo"]:
                g[int(v["start"] * SR):int(v["end"] * SR)] = m["duck"]
            k = max(1, int(m["ramp"] * SR))
            g = np.convolve(np.pad(g, (k // 2, k - 1 - k // 2), mode="edge"), np.ones(k) / k, mode="valid")
            g *= np.minimum(1, np.arange(n) / (0.3 * SR)) * np.minimum(1, (n - np.arange(n)) / (1.0 * SR))
            out += x * g
    for v in tl["vo"]:
        x = load_audio(v["path"])
        a = int(v["start"] * SR)
        x = x[:max(0, n - a)]
        out[a:a + len(x)] += x
    for fx in tl["sfx"]:  # only a soft low "tick" on scenes that ask for it; no noise sweeps (user: they hurt)
        L = int(0.07 * SR)
        tt = np.arange(L) / SR
        clip, a = np.sin(2 * np.pi * 180 * tt) * np.exp(-tt * 60) * np.minimum(1, tt / 0.004), max(0, int(fx["t"] * SR))
        clip = clip[:max(0, n - a)] * tl["sfx_volume"]
        out[a:a + len(clip)] += clip
    peak = np.abs(out).max() if n else 0
    if peak > 0.98:
        out *= 0.98 / peak
    return np.stack([out, out], 1)


def render(tl: dict, out: str):
    from moviepy import AudioArrayClip, VideoClip
    r = Reel(tl)
    clip = VideoClip(r.frame, duration=tl["duration"]).with_audio(AudioArrayClip(mix(tl), fps=SR))
    prev = tl.get("preview")
    clip.write_videofile(out, fps=tl["fps"], codec="libx264", audio_codec="aac", audio_fps=SR,
                         preset="ultrafast" if prev else "medium", threads=4, logger=None,
                         temp_audiofile=out + ".audio.m4a",
                         ffmpeg_params=["-crf", "30" if prev else "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"])
    for v in r.videos.values():
        v.close()


if __name__ == "__main__":
    render(json.loads(open(sys.argv[1]).read()), sys.argv[2])
