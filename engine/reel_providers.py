"""Swappable providers for the Reel Director, one function per kind, each with a free fallback so a reel never blocks
on an API. Every model and tool here is open source / open weight.

kind     REEL_<KIND>_PROVIDER   real                                   fallback
text     llm | mock             engine/llm.py (open model)             template storyboard + rule-based critic
image    openai | none          render._openai (IMAGE_BASE_URL)         uploaded reference or motion graphics
video    none                   no open model host yet (Wan/LTX later)  image or upload with Ken Burns motion
tts      kokoro | piper | silent Kokoro-82M (Apache-2.0; 54 voices incl. silent clip timed at the `wpm` dial
                                Hindi) via kokoro-onnx (MIT); Piper (GPL-3.0) kept as a fallback
timing   whisper | proportional faster-whisper word timestamps (MIT)    per-word share of the clip by length
music    procedural             numpy pad + kick (license-clean)        uploaded track (role=music) wins
stock    openverse | none       Openverse CC images, attribution kept   none
vision   VISION_PROVIDER=vertex Llama 4 on Vertex (open weights), or    measured visual checks only
         or VISION_BASE_URL     any OpenAI-compatible vision server
"""
import hashlib
import json
import os
import re
import threading
import wave
from pathlib import Path

import numpy as np

from . import llm, render

CACHE = Path(os.getenv("REEL_DIR", "data/reels")) / "cache"
VOICE = Path(os.getenv("PIPER_VOICE", "data/voices/en_US-lessac-medium.onnx"))
KOKORO = Path(os.getenv("KOKORO_MODEL", "data/voices/kokoro-v1.0.onnx"))
KOKORO_VOICES = KOKORO.with_name("voices-v1.0.bin")


class NotConfigured(RuntimeError):
    """Provider unavailable; the caller falls back and records why."""


def _env(kind, default):
    return os.getenv(f"REEL_{kind.upper()}_PROVIDER", default).lower()


def _has(module):
    import importlib.util
    return importlib.util.find_spec(module) is not None


def available() -> dict:
    """What each kind will actually use right now (shown in the UI and stored with every asset)."""
    return {
        "text": "mock" if _env("text", "llm") == "mock" or not (os.getenv("LLM_PROVIDER") or os.getenv("LLM_BASE_URL"))
        else "llm",
        "image": "openai" if _env("image", "openai") == "openai" and os.getenv("IMAGE_BASE_URL") else None,
        "video": None,
        "tts": _tts(),
        "timing": "whisper" if _env("timing", "proportional") == "whisper" and _has("faster_whisper") else "proportional",
        "music": "procedural",
        "stock": "openverse" if _env("stock", "none") == "openverse" else None,
        "vision": "vertex" if os.getenv("VISION_PROVIDER") == "vertex" else "openai" if os.getenv("VISION_BASE_URL")
        else None,
    }


def _tts() -> str:
    want = _env("tts", "kokoro")
    kokoro = _has("kokoro_onnx") and KOKORO.exists() and KOKORO_VOICES.exists()
    piper = _has("piper") and VOICE.exists()
    if want == "kokoro" and kokoro:
        return "kokoro"
    if want in ("kokoro", "piper") and piper:
        return "piper"
    return "kokoro" if want != "silent" and kokoro else "silent"


def key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:20]


def cached(k: str, ext: str, make) -> Path:
    """Content-addressed: a retry or page refresh with the same inputs never pays for a generation twice."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{k}{ext}"
    if not path.exists():
        data = make()
        tmp = path.with_suffix(ext + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path


# ---------- text ----------

def text_json(system: str, user: str, temperature: float = 0.6) -> dict:
    if available()["text"] == "mock":
        raise NotConfigured("no text model configured (LLM_PROVIDER / LLM_BASE_URL), using the template director")
    return llm.chat_json(system, user, temperature)


def vision_json(system: str, user: str, images: list[bytes], temperature: float = 0.2) -> dict:
    if not available()["vision"]:
        raise NotConfigured("no vision model (set VISION_PROVIDER=vertex or VISION_BASE_URL)")
    return llm.vision_json(system, user, images, temperature)


# ---------- visuals ----------

def image(prompt: str, negative: str, refs: list[str], nonce: int = 0) -> tuple[Path, dict]:
    if not available()["image"]:
        raise NotConfigured("no image model configured (set IMAGE_BASE_URL to an open-weight model's endpoint)")
    model = os.getenv("IMAGE_MODEL", "flux.1-schnell")
    # ponytail: the OpenAI images API takes no reference images; references are described in the prompt.
    full = f"{prompt}\nAvoid: {negative}" if negative else prompt
    path = cached(key("image", model, full, refs, nonce), ".png", lambda: render._openai(full, "9:16"))
    return path, {"provider": "openai-compatible", "model": model}


def video(prompt: str, image_path: str | None, seconds: float) -> tuple[Path, dict]:
    raise NotConfigured("no open video model hosted yet (e.g. Wan 2.x or LTX-Video); using a still with camera motion")


def stock(query: str, timeout: float) -> tuple[Path, dict]:
    if not available()["stock"]:
        raise NotConfigured("stock search off (set REEL_STOCK_PROVIDER=openverse)")
    import io
    import httpx
    from PIL import Image
    r = httpx.get("https://api.openverse.org/v1/images/", timeout=timeout,
                  params={"q": query[:120], "license_type": "commercial,modification",  # captions = a derivative: no ND
                          "aspect_ratio": "tall", "page_size": 6})
    r.raise_for_status()
    for hit in r.json().get("results") or []:
        try:  # hosts behind Openverse sometimes answer with HTML or a tiny placeholder: keep only real photos
            data = httpx.get(hit["url"], timeout=timeout, follow_redirects=True,
                             headers={"User-Agent": "MarkStrap/0.1"}).content
            im = Image.open(io.BytesIO(data))
            im.load()
            if min(im.size) < 300:
                continue
        except Exception:
            continue
        path = cached(key("stock", hit["url"]), ".img", lambda: data)
        return path, {"provider": "openverse", "source": hit.get("foreign_landing_url"),
                      "attribution": hit.get("attribution") or f"{hit.get('title')} by {hit.get('creator')} ({hit.get('license')})"}
    raise NotConfigured(f"no usable stock photo for '{query[:40]}'")


# ---------- audio ----------

def _write_wav(path: Path, samples: np.ndarray, sr: int):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def wav_seconds(path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


_engines = {}


def tts(text: str, wpm: float, voice: str = "af_heart", speed: float = 1.0, lang: str = "en-us") -> tuple[Path, dict]:
    """One voiceover clip. `voice`/`speed`/`lang` apply to Kokoro; Piper has one voice; silent is timed at wpm."""
    prov = available()["tts"]

    def make():
        out = CACHE / f"tmp-{os.getpid()}-{threading.get_ident()}.wav"
        if prov == "kokoro":
            from kokoro_onnx import Kokoro
            k = _engines.get("kokoro") or _engines.setdefault("kokoro", Kokoro(str(KOKORO), str(KOKORO_VOICES)))
            samples, sr = k.create(text, voice=voice, speed=speed, lang=lang)
            _write_wav(out, np.asarray(samples), sr)
        elif prov == "piper":
            from piper import PiperVoice
            v = _engines.get("piper") or _engines.setdefault("piper", PiperVoice.load(str(VOICE)))
            with wave.open(str(out), "wb") as w:
                v.synthesize_wav(text, w)
        else:
            _write_wav(out, np.zeros(int(max(0.3, len(text.split()) / wpm * 60) * 22050)), 22050)
        data = out.read_bytes()
        out.unlink()
        return data

    who = {"kokoro": (voice, speed, lang), "piper": VOICE.name, "silent": wpm}[prov]
    path = cached(key("tts", prov, who, text), ".wav", make)
    return path, {"provider": prov, "voice": voice if prov == "kokoro" else VOICE.stem if prov == "piper" else None}


def word_times(path, text: str) -> list[list]:
    """[[word, start, end], ...] in seconds from the start of the clip."""
    dur = wav_seconds(path)
    if available()["timing"] == "whisper":
        from faster_whisper import WhisperModel
        segs, _ = WhisperModel(os.getenv("WHISPER_MODEL", "base.en")).transcribe(str(path), word_timestamps=True)
        out = [[w.word.strip(), w.start, w.end] for s in segs for w in s.words]
        if out:
            return out
    words = text.split()
    if not words:
        return []
    # Proportional: longer words take longer to say. Leaves the clip's lead-in/out silence (~6%) at the edges.
    lead, span = dur * 0.03, dur * 0.94
    w = np.array([len(re.sub(r"\W", "", x)) + 2 for x in words], float)
    edges = lead + np.concatenate([[0], np.cumsum(w)]) / w.sum() * span
    return [[x, round(float(edges[i]), 3), round(float(edges[i + 1]), 3)] for i, x in enumerate(words)]


def music(seconds: float, seed: str, bpm: int = 96) -> tuple[Path, dict]:
    """Soft four-chord pad with a light kick, deterministic per seed. No samples, no licences to track."""
    def make():
        sr = 22050
        t = np.arange(int(seconds * sr)) / sr
        rng = np.random.default_rng(int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16))
        roots = [57, 53, 60, 55][rng.integers(4):] + [57, 53, 60, 55][:rng.integers(4)]
        bar = 4 * 60 / bpm
        out = np.zeros_like(t)
        for i, r in enumerate(roots * int(seconds / bar / 4 + 2)):
            a, b = i * bar, (i + 1) * bar
            if a >= seconds:
                break
            m = (t >= a) & (t < b)
            lt = t[m] - a
            env = np.minimum(1, lt / 0.4) * np.minimum(1, (bar - lt) / 0.4)
            for semis in (0, 4 if i % 2 == 0 else 3, 7, 12):
                f = 440 * 2 ** ((r + semis - 69) / 12)
                out[m] += 0.08 * env * np.sin(2 * np.pi * f * t[m])
        beat = 60 / bpm
        kt = t % beat
        out += 0.25 * np.exp(-kt * 18) * np.sin(2 * np.pi * (50 + 60 * np.exp(-kt * 30)) * kt)
        p = CACHE / f"tmp-m-{os.getpid()}.wav"
        _write_wav(p, out / max(1e-6, np.abs(out).max()) * 0.8, sr)
        data = p.read_bytes()
        p.unlink()
        return data

    return cached(key("music", seconds, seed, bpm), ".wav", make), {"provider": "procedural", "bpm": bpm}
