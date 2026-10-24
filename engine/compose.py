"""Draw a reel timeline (engine/reel.timeline) into an MP4 with MoviePy + ffmpeg (both open source).

No planning here: every time, position, colour and level comes from the timeline. Text layers are drawn once and
cached; each frame only moves, fades and stacks them. Run: python -m engine.compose timeline.json out.mp4
"""
import json
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
            img = self.motion(i, lt, dur)
        img = img.convert("RGBA")
        last = i == len(self.scenes) - 1
        if last:
            return self.end_card(img, s, lt)
        if s["text"]:
            motion = s["id"] not in self.src and s["id"] not in self.videos
            layer = self.title_layer(s["text"], motion)
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
            self.paste(img, self.cta_layer(self.cta), int(y + (1 - ease((lt - 0.3) / 0.4)) * H * 0.02),
                       ease((lt - 0.3) / 0.4))
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
    rng = np.random.default_rng(7)
    for fx in tl["sfx"]:
        if fx["kind"] == "whoosh":
            L = int(0.4 * SR)
            noise = np.convolve(rng.standard_normal(L), np.ones(24) / 24, mode="same")
            e = np.sin(np.linspace(0, np.pi, L)) ** 2
            clip, a = noise * e * 2.2, int((fx["t"] - 0.25) * SR)
        else:  # pop
            L = int(0.09 * SR)
            tt = np.arange(L) / SR
            clip, a = np.sin(2 * np.pi * (900 - 6000 * tt) * tt) * np.exp(-tt * 45), int(fx["t"] * SR)
        a = max(0, a)
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
