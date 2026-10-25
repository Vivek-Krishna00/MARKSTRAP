"""Reel Director: an approved concept -> brief -> validated storyboard -> assets, voice, captions -> critic with
targeted repair -> 9:16 MP4.

All planning lives here (spec, prompts, continuity, timeline). engine/compose.py only draws the timeline it is given.
Every scene keeps its own status, error and input hashes, so a run resumes where it stopped and a change re-makes
only the scenes it touches. Paid generations are content-addressed (reel_providers.cached).
"""
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator, model_validator

from . import evolve
from . import reel_providers as P

CFG = evolve.CFG["reel"]
ROOT = Path(P.CACHE).parent
DEMO = Path(__file__).resolve().parent / "data" / "reel_demo.json"
CRITERIA = ["hook", "clarity", "visual_relevance", "brand_consistency", "product_accuracy", "continuity", "pacing",
            "caption_readability", "audio_balance", "cta_clarity", "platform_fit", "visual_quality"]
VISUAL = ["hook", "visual_relevance", "brand_consistency", "product_accuracy", "continuity", "caption_readability",
          "platform_fit", "visual_quality"]  # what the frames can show; the vision judge scores only these
ROLES = ["product", "character", "location", "style", "logo", "music", "font", "reference_reel"]
KINDS = {"image": {".png", ".jpg", ".jpeg", ".webp"}, "video": {".mp4", ".mov", ".webm", ".m4v"},
         "audio": {".mp3", ".wav", ".m4a", ".ogg"}, "font": {".ttf", ".otf"}}
PLATFORMS = {"instagram": "instagram_reels", "tiktok": "tiktok", "youtube": "youtube_shorts"}
DEFAULT_COLORS = ["#080A0E", "#F0F1ED", "#91D0FF"]
STAGES = ["assets", "voice", "captions", "critic", "preview", "review"]

# ---------- schema (validated; everything the model returns goes through it) ----------

Purpose = Literal["hook", "problem", "demonstration", "proof", "payoff", "cta"]
AssetType = Literal["generated_video", "generated_image", "uploaded_asset", "stock_video", "motion_graphics"]


class Camera(BaseModel):
    shot: str = "medium close-up"
    movement: str = "slow push-in"
    lensOrPerspective: str = "35mm, eye level"


class Scene(BaseModel):
    id: str
    startSeconds: float = Field(ge=0)
    endSeconds: float = Field(gt=0)
    purpose: Purpose
    voiceover: str = ""
    onScreenText: str = ""
    visualDescription: str
    assetType: AssetType = "motion_graphics"
    # Structured prompt parts: the director fills them, scene_prompt() always assembles a complete prompt.
    subject: str = ""
    action: str = ""
    environment: str = ""
    composition: str = ""
    lighting: str = ""
    motion: str = ""
    productPlacement: str = ""
    emotion: str = ""
    generationPrompt: str = ""
    negativePrompt: str = ""
    referenceAssetIds: list[str] = []
    camera: Camera = Camera()
    transitionOut: str = "cut"
    soundEffect: str = ""
    continuityNotes: str = ""

    @field_validator("referenceAssetIds")
    @classmethod
    def refs_exist(cls, v, info: ValidationInfo):
        known = (info.context or {}).get("assets")
        if known is not None:
            bad = [x for x in v if x not in known]
            if bad:
                raise ValueError(f"unknown reference asset ids {bad}; use only {sorted(known)}")
        return v


class CreativeDirection(BaseModel):
    tone: str
    visualStyle: str
    colorDirection: list[str] = []
    editingStyle: str = "fast cuts on the beat"
    musicDirection: str = "light, warm, mid-tempo"


class Hook(BaseModel):
    spokenText: str
    onScreenText: str
    visualAction: str


class Voiceover(BaseModel):
    fullScript: str
    voiceDirection: str = "warm, confident, conversational"


class CaptionStyle(BaseModel):
    position: str = "bottom"
    font: str = "Manrope ExtraBold"
    colors: list[str] = ["#FFFFFF", "#91D0FF"]
    animation: str = "word-by-word highlight"


class CTA(BaseModel):
    spokenText: str
    onScreenText: str


class Continuity(BaseModel):
    product: str = ""
    character: str = ""
    environment: str = ""
    lighting: str = ""
    style: str = ""
    screenDirection: str = "subject moves left to right; keep eyelines consistent"


class ReelSpec(BaseModel):
    title: str
    objective: str
    audience: str
    platform: Literal["instagram_reels", "tiktok", "youtube_shorts"]
    aspectRatio: Literal["9:16"] = "9:16"
    durationSeconds: float = Field(ge=6, le=90)
    creativeDirection: CreativeDirection
    hook: Hook
    voiceover: Voiceover
    scenes: list[Scene] = Field(min_length=2, max_length=20)
    captionStyle: CaptionStyle = CaptionStyle()
    callToAction: CTA
    continuity: Continuity = Continuity()

    @model_validator(mode="after")
    def timing(self):
        ids = [s.id for s in self.scenes]
        if len(set(ids)) != len(ids):
            raise ValueError("scene ids must be unique")
        t = 0.0
        for s in self.scenes:
            if abs(s.startSeconds - t) > 0.05:
                raise ValueError(f"{s.id} starts at {s.startSeconds}s; scenes must be contiguous (expected {t:g}s)")
            if s.endSeconds - s.startSeconds < CFG["min_scene_s"] - 1e-6:
                raise ValueError(f"{s.id} is shorter than {CFG['min_scene_s']}s")
            t = s.endSeconds
        if abs(t - self.durationSeconds) > 0.1:
            raise ValueError(f"scenes end at {t:g}s but durationSeconds is {self.durationSeconds:g}")
        if self.scenes[0].endSeconds > CFG["hook_max_s"] + 1e-6:
            raise ValueError(f"the first scene (hook) must end by {CFG['hook_max_s']}s")
        return self


def validate(data: dict, asset_ids) -> ReelSpec:
    return ReelSpec.model_validate(data, context={"assets": set(asset_ids)})


# ---------- store ----------

def _j(v):
    return json.dumps(v) if v is not None else None


def _row(r):
    d = dict(r)
    for k in ("brief", "spec", "critic", "renders", "log", "asset", "audio", "meta"):
        if d.get(k):
            d[k] = json.loads(d[k])
    return d


def folder(reel_id: str) -> Path:
    p = ROOT / safe_name(reel_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_name(name: str) -> str:
    stem = re.sub(r"[^a-z0-9._-]+", "-", Path(name or "file").name.lower()).strip("-.")
    return stem[:80] or "file"


def save(con, reel_id, **f):
    f["updated"] = time.time()
    for k in ("brief", "spec", "critic", "renders", "log"):
        if k in f:
            f[k] = _j(f[k])
    con.execute(f"UPDATE reels SET {', '.join(f'{k}=?' for k in f)} WHERE id=?", (*f.values(), reel_id))
    con.commit()


def scene_state(con, reel_id) -> dict:
    return {r["scene_id"]: _row(r) for r in con.execute("SELECT * FROM reel_scenes WHERE reel_id=?", (reel_id,))}


def save_scene(con, reel_id, sid, **f):
    con.execute("INSERT OR IGNORE INTO reel_scenes (reel_id, scene_id) VALUES (?,?)", (reel_id, sid))
    for k in ("asset", "audio"):
        if k in f:
            f[k] = _j(f[k])
    if f:
        con.execute(f"UPDATE reel_scenes SET {', '.join(f'{k}=?' for k in f)} WHERE reel_id=? AND scene_id=?",
                    (*f.values(), reel_id, sid))
    con.commit()


def assets(con, reel_id) -> list[dict]:
    return [_row(r) for r in con.execute("SELECT * FROM reel_assets WHERE reel_id=? ORDER BY rowid", (reel_id,))]


def load(con, reel_id) -> dict:
    r = con.execute("SELECT * FROM reels WHERE id=?", (reel_id,)).fetchone()
    if not r:
        raise KeyError(reel_id)
    return _row(r)


def view(con, reel_id) -> dict:
    """Everything the UI needs: reel, scenes with their state and composed prompt, assets, providers."""
    busy = reel_id in _running  # read first: "not busy" then means the data below is from after the run
    r = load(con, reel_id)
    st = scene_state(con, reel_id)
    r["scenes"] = [{**s, "state": st.get(s["id"], {})} for s in (r.get("spec") or {}).get("scenes", [])]
    r["assets"] = assets(con, reel_id)
    r["providers"] = P.available()
    r["busy"] = busy
    return r


# ---------- 1. brief ----------

def prefill(ad: dict, campaign: dict) -> dict:
    """Reel brief from what the app already knows; the user edits it before the storyboard."""
    c, b, k = ad["content"], campaign.get("brief") or {}, campaign.get("constraints") or {}
    rules = " ".join(str(v) for v in k.values())
    colors = re.findall(r"#[0-9a-fA-F]{6}\b", rules) or DEFAULT_COLORS
    return {
        "idea": f"{c.get('headline', '').rstrip('.!? ')}. {c.get('body', '')}".strip(". "),
        "seen": c.get("seen", ""), "style": c.get("visual", ""),
        "product": b.get("offering", campaign.get("goal", "")),
        "audience": b.get("audience", campaign.get("market", "")),
        "objective": b.get("goal", campaign.get("goal", "")),
        "keyMessages": b.get("key_messages", []), "proof": b.get("proof_points", []),
        "platform": PLATFORMS.get((c.get("platform") or "").lower(), "instagram_reels"),
        "durationSeconds": CFG["duration_s"],
        "brandVoice": k.get("brand_rules") or "warm, specific, no hype",
        "language": k.get("language") or "English", "speaker": "auto",
        "colors": colors[:4], "fonts": ["Manrope"],
        "cta": b.get("action") or b.get("destination") or "Link in bio",  # a sentence reads better on screen than a URL
        "mustNot": k.get("restricted_claims") or "",
        "notes": "",
        "voice": "on", "captions": "on", "voiceStyle": "", "musicDirection": "",
    }


# ---------- 2. director ----------

def _plan(duration: float) -> list[tuple[str, float, float]]:
    """Purposes and timing for a template storyboard: 2.5 s hook, 3.5 s CTA, the rest split evenly."""
    hook = min(2.5, CFG["hook_max_s"])
    cta = round(max(CFG["min_scene_s"], min(3.5, (duration - hook) * 0.4)), 2)
    mids = ["problem", "demonstration", "proof", "payoff"][:max(1, min(4, round((duration - hook - cta) / 3.5)))]
    step = (duration - hook - cta) / len(mids)
    cuts = [0, hook] + [round(hook + step * (i + 1), 2) for i in range(len(mids))]
    cuts[-1] = duration - cta
    plan = [("hook", cuts[0], cuts[1])] + [(p, cuts[i + 1], cuts[i + 2]) for i, p in enumerate(mids)]
    return plan + [("cta", duration - cta, duration)]


def template_spec(brief: dict, asset_list: list[dict]) -> dict:
    """The no-model director: a sound storyboard from the brief alone, so the demo never blocks on an API."""
    D = float(brief.get("durationSeconds") or CFG["duration_s"])
    said = re.sub(r"\b\d+(-\d+)?s:|\b(Text|Voice|VO|Audio):", " ", brief.get("idea", ""))
    lines = brief.get("keyMessages", []) + brief.get("proof", []) + \
        [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", said) if len(x.split()) >= 3]
    lines = lines[1:] if len(lines) > 1 and lines[0] == said else lines or [brief.get("product", "")]
    imgs = [a for a in asset_list if a["kind"] in ("image", "video") and a["role"] in ("product", "character", "location")]
    head = (brief.get("idea") or brief.get("product") or "").split(". ")[0]
    scenes = []
    for i, (purpose, a, b) in enumerate(_plan(D)):
        line = head if purpose == "hook" else brief.get("cta", "") if purpose == "cta" else lines[(i - 1) % len(lines)]
        ref = imgs[(i - 1) % len(imgs)] if imgs and purpose not in ("hook", "cta") else None
        scenes.append({
            "id": f"scene-{i + 1:02d}", "startSeconds": a, "endSeconds": b, "purpose": purpose,
            "voiceover": line, "onScreenText": " ".join(line.split()[:6]),
            "visualDescription": f"{purpose}: {brief.get('style') or brief.get('product')}",
            "assetType": "uploaded_asset" if ref else "motion_graphics",
            "subject": brief.get("product", ""), "action": line, "referenceAssetIds": [ref["id"]] if ref else [],
            "transitionOut": "crossfade" if purpose != "cta" else "cut",
            "soundEffect": ""})
    return {
        "title": head[:80] or "Reel", "objective": brief.get("objective", ""), "audience": brief.get("audience", ""),
        "platform": brief.get("platform", "instagram_reels"), "durationSeconds": D,
        "creativeDirection": {"tone": brief.get("brandVoice", ""), "visualStyle": brief.get("style") or "clean, bold",
                              "colorDirection": brief.get("colors", [])},
        "hook": {"spokenText": head, "onScreenText": " ".join(head.split()[:6]), "visualAction": "bold type slams in"},
        "voiceover": {"fullScript": " ".join(s["voiceover"] for s in scenes)},
        "scenes": scenes,
        "captionStyle": {"colors": ["#FFFFFF", (brief.get("colors") or DEFAULT_COLORS)[-1]]},
        "callToAction": {"spokenText": brief.get("cta", ""), "onScreenText": brief.get("cta", "")[:32]},
        "continuity": {"product": brief.get("product", ""), "style": brief.get("style", "")}}


DIRECTOR = (
    "You are a Reel director at a marketing agency. You turn one approved ad concept into a scene-by-scene vertical "
    "short-form storyboard that a production pipeline renders without a human. Specific beats generic. The first "
    "three seconds must stop the scroll. Each scene says one thing. Never make claims the brief forbids.")


def _schema_hint(brief, asset_list, avail):
    types = ["motion_graphics"] + (["uploaded_asset"] if asset_list else []) + \
            (["generated_image"] if avail["image"] else []) + (["stock_video"] if avail["stock"] else [])
    return (
        f"Return the ReelSpec JSON: title, objective, audience, platform ({brief['platform']}), aspectRatio \"9:16\", "
        f"durationSeconds {brief['durationSeconds']}, creativeDirection {{tone, visualStyle, colorDirection[], "
        "editingStyle, musicDirection}, hook {spokenText, onScreenText, visualAction}, voiceover {fullScript, "
        "voiceDirection}, scenes[], captionStyle {position, font, colors[], animation}, callToAction {spokenText, "
        "onScreenText}, continuity {product, character, environment, lighting, style, screenDirection}.\n"
        "Each scene: id (scene-01...), startSeconds, endSeconds, purpose (hook|problem|demonstration|proof|payoff|cta), "
        "voiceover, onScreenText, visualDescription, assetType, subject, action, environment, composition, lighting, "
        "motion, productPlacement, emotion, negativePrompt, referenceAssetIds[], camera {shot, movement, "
        "lensOrPerspective}, transitionOut (cut|crossfade|slide|whip), soundEffect (pop|none), continuityNotes.\n"
        f"Rules: scenes are contiguous from 0 to {brief['durationSeconds']}s, {CFG['min_scene_s']}-5 s each; the first "
        f"scene is the hook and ends by {CFG['hook_max_s']}s; the last is the cta. Voiceover fits the scene at "
        f"{CFG['wpm']} words per minute. onScreenText at most {CFG['onscreen_max_chars']} characters. "
        f"assetType only from {types}. referenceAssetIds only from the asset list.")


def direct(brief: dict, asset_list: list[dict]) -> tuple[dict, str]:
    """Storyboard via the text model, validated; one re-ask with the error, then the template director."""
    avail = P.available()
    ids = [a["id"] for a in asset_list]
    refs = [{k: a[k] for k in ("id", "role", "kind", "name")} | {"note": (a.get("meta") or {}).get("note", "")}
            for a in asset_list]
    user = (f"Brief:\n{json.dumps(brief, indent=1)}\n\nReference assets:\n{json.dumps(refs)}\n\n"
            f"{_schema_hint(brief, asset_list, avail)}")
    err = None
    for _ in range(1 + CFG["director_retries"]):
        try:
            data = P.text_json(DIRECTOR, user + (f"\n\nYour last answer failed validation: {err}. Fix it." if err else ""),
                               temperature=0.6)
            return validate(data, ids).model_dump(), "llm"
        except P.NotConfigured:
            break
        except (ValidationError, ValueError) as e:
            err = str(e)[:800]
    spec = validate(template_spec(brief, asset_list), ids).model_dump()
    return spec, "template" + (f" (model output kept failing validation: {err[:200]})" if err else "")


# ---------- 3. continuity + prompts ----------

def continuity(spec: dict, brief: dict, asset_list: list[dict]) -> dict:
    """Reusable profile every scene prompt inherits: spec continuity + brand + what each reference must keep."""
    c = dict(spec.get("continuity") or {})
    c["brand"] = f"palette {', '.join(brief.get('colors') or DEFAULT_COLORS)}; type {', '.join(brief.get('fonts') or ['Manrope'])}"
    keep = {"product": "exact shape, label text, colours and logo placement",
            "character": "same face, hair, skin tone, build and clothing",
            "location": "same set, props and time of day", "style": "same grade, texture and framing language",
            "logo": "logo unaltered, never redrawn"}
    c["references"] = {a["id"]: f"{a['role']} '{a['name']}': keep {keep.get(a['role'], 'its look')}"
                       + (f" ({a['meta']['note']})" if (a.get("meta") or {}).get("note") else "")
                       for a in asset_list if a["role"] in keep}
    return c


NEGATIVE = ("no on-image text or captions, no watermarks, no extra or invented logos, no warped labels, "
            "no distorted hands or faces, no horizontal framing, no letterboxing")


def scene_prompt(s: dict, spec: dict, profile: dict) -> tuple[str, str]:
    """Production prompt assembled from structured fields, so every element is always present."""
    cd, cam, dur = spec["creativeDirection"], s["camera"], s["endSeconds"] - s["startSeconds"]
    refs = [profile["references"][r] for r in s["referenceAssetIds"] if r in profile.get("references", {})]
    cont = "; ".join(f"{k}: {v}" for k, v in profile.items() if k not in ("references",) and v)
    parts = [
        ("Subject", s["subject"] or spec["continuity"].get("product") or s["visualDescription"]),
        ("Action", s["action"] or s["visualDescription"]),
        ("Environment", s["environment"] or profile.get("environment") or "uncluttered setting that fits the brand"),
        ("Composition", (s["composition"] or "single clear focal point") +
         "; vertical 9:16, subject in the centre band, top 13% and bottom 25% kept clear for platform UI and captions"),
        ("Camera", f"{cam['shot']}, {cam['lensOrPerspective']}"),
        ("Camera movement", cam["movement"]),
        ("Lighting", s["lighting"] or profile.get("lighting") or "soft key light, gentle contrast"),
        ("Visual style", cd["visualStyle"]),
        ("Color palette", ", ".join(cd.get("colorDirection") or []) or profile["brand"]),
        ("Emotional tone", s["emotion"] or cd["tone"]),
        ("Duration", f"{dur:.1f} s shot, aspect ratio 9:16"),
        ("Motion", s["motion"] or "smooth, natural motion; no sudden jumps"),
        ("Product placement", s["productPlacement"] or "product visible and recognisable, label facing camera"),
        ("References", "; ".join(refs) or "none"),
        ("Continuity", "; ".join(x for x in (cont, s["continuityNotes"]) if x)),
    ]
    negative = "; ".join(x for x in (s["negativePrompt"], NEGATIVE) if x)
    return "\n".join(f"{k}: {v}" for k, v in parts) + f"\nExclusions: {negative}", negative


def words_budget(s: dict) -> int:
    return max(2, int((s["endSeconds"] - s["startSeconds"] - 0.3) * CFG["wpm"] / 60))


def _clip_words(text: str, n: int) -> str:
    """At most n words, cut at the last clause boundary that fits so the line still reads as a sentence."""
    w = text.split()
    if len(w) <= n:
        return text
    cut = max((i + 1 for i in range(n) if re.search(r"[.!?,;:]$", w[i])), default=n)
    return " ".join(w[:cut]).rstrip(",;:") + ("" if re.search(r"[.!?]$", w[cut - 1]) else ".")


def _clip_chars(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",;:.-")


def finalize(spec: dict, brief: dict, asset_list: list[dict]) -> dict:
    """Deterministic pass after every edit: fit text to time, inherit continuity, compose prompts, sync scripts."""
    profile = continuity(spec, brief, asset_list)
    for s in spec["scenes"]:
        s["voiceover"] = _clip_words(s["voiceover"], words_budget(s))
        s["onScreenText"] = _clip_chars(s["onScreenText"], CFG["onscreen_max_chars"])
        s["generationPrompt"], s["negativePrompt"] = scene_prompt(s, spec, profile)
    spec["voiceover"]["fullScript"] = " ".join(s["voiceover"] for s in spec["scenes"] if s["voiceover"])
    spec["profile"] = profile
    return spec


# ---------- hashes: what a scene's visual / voice was made from ----------

def visual_hash(s, st, avail):
    return P.key(s["assetType"], s["generationPrompt"], s["referenceAssetIds"], st.get("regen") or 0,
                 avail["image"], avail["stock"], st.get("replaced"))


VOICES = {  # Kokoro voices: (female, male) per language; the brief can name any of the 54 directly
    "en-us": ("af_heart", "am_michael"), "en-gb": ("bf_emma", "bm_george"), "hi": ("hf_alpha", "hm_omega")}


def voice_for(spec: dict, brief: dict) -> tuple[str, float, str]:
    """Voice, speed and language from the brief and the director's voice direction. Deterministic."""
    direction = (f"{brief.get('voiceStyle', '')} {spec['voiceover'].get('voiceDirection', '')} "
                 f"{brief.get('brandVoice', '')}").lower()
    language = (brief.get("language") or "English").lower()
    lang = "hi" if "hindi" in language else "en-gb" if "british" in direction else "en-us"
    male = bool(re.search(r"\b(male|man|deep|baritone|guy)\b", direction)) and "female" not in direction
    voice = brief.get("speaker") if brief.get("speaker") not in (None, "", "auto") else VOICES[lang][male]
    speed = (CFG["voice_speed_fast"] if re.search(r"energetic|punchy|quick|fast|hype|excited", direction)
             else CFG["voice_speed_calm"] if re.search(r"calm|slow|soothing|gentle|soft", direction)
             else CFG["voice_speed"])
    return voice, speed, lang


def audio_hash(s, avail, voice=None):
    return P.key(s["voiceover"], avail["tts"], CFG["wpm"], voice)


# ---------- 4. production stages ----------

def _asset_by_id(asset_list):
    return {a["id"]: a for a in asset_list}


def make_visual(s: dict, st: dict, asset_list: list[dict]) -> dict:
    """One scene's picture. Tries the scene's asset type, then falls back down a free chain; records why."""
    byid = _asset_by_id(asset_list)
    if st.get("replaced"):  # user replaced this one scene's media
        a = byid.get(st["replaced"])
        if a:
            return {"kind": a["kind"], "path": a["path"], "provider": "upload", "fallback": None}
    refs = [byid[r] for r in s["referenceAssetIds"] if r in byid and byid[r]["kind"] in ("image", "video")]
    tried = []
    order = {"generated_video": ["video", "image", "upload"], "generated_image": ["image", "upload"],
             "stock_video": ["stock", "upload"], "uploaded_asset": ["upload"], "motion_graphics": []}[s["assetType"]]
    for how in order:
        try:
            if how == "upload":
                if not refs:
                    raise P.NotConfigured("no image or video assigned to this scene")
                return {"kind": refs[0]["kind"], "path": refs[0]["path"], "provider": "upload",
                        "fallback": "; ".join(tried) or None}
            if how == "video":
                path, meta = P.video(s["generationPrompt"], refs[0]["path"] if refs else None,
                                     s["endSeconds"] - s["startSeconds"])
                return {"kind": "video", "path": str(path), **meta, "fallback": None}
            if how == "image":
                path, meta = P.image(s["generationPrompt"], s["negativePrompt"], [r["id"] for r in refs],
                                     st.get("regen") or 0)
            else:
                path, meta = P.stock(s["subject"] or s["visualDescription"], CFG["provider_timeout_s"])
            return {"kind": "image", "path": str(path), **meta, "fallback": "; ".join(tried) or None}
        except P.NotConfigured as e:
            tried.append(str(e))
    return {"kind": "motion", "path": None, "provider": "motion_graphics", "fallback": "; ".join(tried) or None}


def stage_assets(con, reel_id, spec, asset_list):
    avail, st = P.available(), scene_state(con, reel_id)
    for s in spec["scenes"]:
        cur = st.get(s["id"], {})
        h = visual_hash(s, cur, avail)
        if (cur.get("asset") or {}).get("hash") == h and cur.get("status") == "done":
            continue
        save_scene(con, reel_id, s["id"], status="running", error=None)
        try:
            a = make_visual(s, cur, asset_list)
            save_scene(con, reel_id, s["id"], status="done", asset={**a, "hash": h},
                       attempts=(cur.get("attempts") or 0) + 1)
        except Exception as e:  # provider outage: keep the reel renderable, show the error on this scene only
            save_scene(con, reel_id, s["id"], status="failed", error=f"{type(e).__name__}: {str(e)[:240]}",
                       asset={"kind": "motion", "path": None, "provider": "motion_graphics", "hash": None,
                              "fallback": "generation failed"}, attempts=(cur.get("attempts") or 0) + 1)


def stage_voice(con, reel_id, spec, brief=None):
    avail, st = P.available(), scene_state(con, reel_id)
    brief = brief if brief is not None else load(con, reel_id)["brief"]
    mute = brief.get("voice") == "off"
    v = voice_for(spec, brief)
    for s in spec["scenes"]:
        cur = st.get(s["id"], {})
        h = audio_hash(s, avail, v) + ("-mute" if mute else "")
        if (cur.get("audio") or {}).get("hash") == h:
            continue
        if mute or not s["voiceover"].strip():
            save_scene(con, reel_id, s["id"], audio={"hash": h, "path": None, "duration": 0, "words": []})
            continue
        path, meta = P.tts(s["voiceover"], CFG["wpm"], *v)
        save_scene(con, reel_id, s["id"], audio={"hash": h, "path": str(path), "duration": P.wav_seconds(path),
                                                  **meta, "words": None})


def stage_captions(con, reel_id, spec):
    st = scene_state(con, reel_id)
    for s in spec["scenes"]:
        au = st.get(s["id"], {}).get("audio") or {}
        if au.get("path") and au.get("words") is None:
            save_scene(con, reel_id, s["id"], audio={**au, "words": P.word_times(au["path"], s["voiceover"])})


# ---------- 5. timeline (deterministic; compose.py draws it) ----------

def timeline(spec: dict, brief: dict, st: dict, asset_list: list[dict], preview: bool, seed: str) -> dict:
    W, H = CFG["preview_size"] if preview else CFG["size"]
    k = W / CFG["size"][0]
    D = spec["durationSeconds"]
    byrole = {}
    for a in asset_list:
        byrole.setdefault(a["role"], a)
    scenes, words, vo = [], [], []
    for i, s in enumerate(spec["scenes"]):
        a, au = st.get(s["id"], {}).get("asset") or {}, st.get(s["id"], {}).get("audio") or {}
        t0, t1 = s["startSeconds"], s["endSeconds"]
        tr = s["transitionOut"].lower()
        scenes.append({"id": s["id"], "start": t0, "end": t1, "purpose": s["purpose"],
                       "kind": a.get("kind") or "motion", "path": a.get("path"), "text": s["onScreenText"],
                       "transition": next((x for x in ("crossfade", "slide", "whip") if x in tr), "cut"),
                       "zoom": [1.0, 1 + CFG["ken_burns"]] if i % 2 == 0 else [1 + CFG["ken_burns"], 1.0],
                       "pan": [(-1) ** i * 0.04, 0.03]})
        if au.get("path"):
            start = t0 + 0.12  # breath after the cut
            vo.append({"path": au["path"], "start": start, "end": min(D, start + au["duration"])})
            words += [{"w": w, "t0": round(start + a0, 3), "t1": round(min(t1, start + a1), 3)}
                      for w, a0, a1 in (au.get("words") or []) if start + a0 < t1]
    music = byrole.get("music")
    sfx = [{"kind": "pop", "t": sc["startSeconds"]} for sc in spec["scenes"] if "pop" in sc["soundEffect"].lower()]
    font = byrole.get("font")
    return {
        "size": [W, H], "fps": CFG["preview_fps"] if preview else CFG["fps"], "duration": D, "preview": preview,
        "safe": {"top": int(CFG["safe_top"] * k), "bottom": int(CFG["safe_bottom"] * k), "side": int(CFG["safe_side"] * k)},
        "colors": brief.get("colors") or DEFAULT_COLORS,
        "caption": {**spec["captionStyle"], "words": CFG["caption_words"], "max_chars": CFG["caption_max_chars"]},
        "font": font["path"] if font else str(Path(__file__).resolve().parent / "data" / "fonts" / "Manrope.ttf"),
        "scenes": scenes, "words": [] if brief.get("captions") == "off" else words, "vo": vo,
        "music": {"path": music["path"] if music else str(P.music(D + 1, seed)[0]), "volume": CFG["music_volume"],
                  "duck": CFG["duck_volume"], "ramp": CFG["duck_ramp_s"]},
        "sfx": sfx, "sfx_volume": CFG["sfx_volume"], "transition_s": CFG["transition_s"],
        "texture": {"dither": CFG["texture_dither_alpha"], "ascii": CFG["texture_ascii_alpha"]},
        "logo": byrole["logo"]["path"] if "logo" in byrole and byrole["logo"]["kind"] == "image" else None,
        "cta": spec["callToAction"]["onScreenText"], "title": spec["title"],
    }


def compose(tl: dict, out: Path):
    """Render in a subprocess: a hung encoder can't take the API down, and the timeout is enforced."""
    tl_path = out.with_suffix(".json")
    tl_path.write_text(json.dumps(tl))
    tmp = out.with_name(out.stem + ".part.mp4")
    r = subprocess.run([sys.executable, "-m", "engine.compose", str(tl_path), str(tmp)], capture_output=True,
                       text=True, timeout=CFG["render_timeout_s"])
    if r.returncode != 0:
        raise RuntimeError(f"render failed: {(r.stderr or r.stdout)[-400:]}")
    tmp.replace(out)


# ---------- 6. critic + targeted repair ----------

def checks(spec: dict, st: dict, brief: dict, asset_list: list[dict]) -> list[dict]:
    """Rule-based review: things that are measurable don't need a model's opinion."""
    out = []

    def add(criterion, sid, target, severity, problem, fix, **extra):
        out.append({"criterion": criterion, "sceneId": sid, "target": target, "severity": severity,
                    "problem": problem, "fix": fix, "source": "rules", **extra})
    sc = spec["scenes"]
    has_product = any(a["role"] == "product" for a in asset_list)
    for s in sc:
        cur, dur = st.get(s["id"], {}), s["endSeconds"] - s["startSeconds"]
        au = cur.get("audio") or {}
        if au.get("duration", 0) > dur + 0.2:
            # Measured, not estimated: numbers and symbols are read out longer than their word count suggests.
            fit = max(2, int(len(s["voiceover"].split()) * (dur - 0.3) / au["duration"]))
            add("pacing", s["id"], "audio", "major", f"voiceover runs {au['duration'] - dur:.1f}s past the scene",
                f"cut the voiceover to {fit} words; write numbers the short way", maxWords=fit)
        if len(s["onScreenText"]) > CFG["onscreen_max_chars"]:
            add("caption_readability", s["id"], "caption", "major", "on-screen text too long to read",
                f"at most {CFG['onscreen_max_chars']} characters")
        if cur.get("status") == "failed":
            add("visual_relevance", s["id"], "scene", "major", f"visual failed: {cur.get('error')}", "retry or replace")
        elif (cur.get("asset") or {}).get("fallback") and s["purpose"] in ("demonstration", "proof") and has_product:
            add("product_accuracy", s["id"], "scene", "minor", "product scene fell back to motion graphics",
                "assign a product image to this scene")
    if not (sc[0]["onScreenText"].strip() and sc[0]["voiceover"].strip()):
        add("hook", sc[0]["id"], "scene", "major", "hook has no spoken line or on-screen text", "add a 3-6 word hook")
    if sc[-1]["purpose"] != "cta" or not spec["callToAction"]["onScreenText"].strip():
        add("cta_clarity", sc[-1]["id"], "scene", "major", "no clear call to action at the end",
            f"end on: {brief.get('cta', 'the destination')}")
    if (brief.get("colors") or DEFAULT_COLORS) == DEFAULT_COLORS:
        add("brand_consistency", None, "scene", "minor", "using MarkStrap's default palette", "add brand colours to the brief")
    return out


class Issue(BaseModel):
    criterion: str = "clarity"
    sceneId: Optional[str] = None
    target: Literal["scene", "caption", "audio", "transition"] = "scene"
    severity: Literal["major", "minor"] = "minor"
    problem: str
    fix: str = ""


class Critique(BaseModel):
    scores: dict[str, float]
    issues: list[Issue] = []

    @field_validator("scores")
    @classmethod
    def all_criteria(cls, v):
        return {c: max(0.0, min(10.0, float(v.get(c, 7)))) for c in CRITERIA}


CRITIC = ("You are a tough short-form video editor reviewing a Reel storyboard before it ships. Score each criterion "
          "0-10 (10 = would stop your own thumb). Name concrete problems tied to a scene id and a fix that changes "
          "only that scene, caption, audio segment or transition.")


def critique(spec, st, brief, asset_list) -> dict:
    rules = checks(spec, st, brief, asset_list)
    scores = {c: 8.0 for c in CRITERIA}
    for i in rules:
        scores[i["criterion"]] -= 3 if i["severity"] == "major" else 1
    issues, by = list(rules), "rules"
    try:
        brief_scenes = [{k: s[k] for k in ("id", "startSeconds", "endSeconds", "purpose", "voiceover", "onScreenText",
                                           "visualDescription", "assetType", "transitionOut")} for s in spec["scenes"]]
        raw = P.text_json(CRITIC, f"Brief: {json.dumps(brief)}\nHook: {json.dumps(spec['hook'])}\n"
                          f"CTA: {json.dumps(spec['callToAction'])}\nScenes: {json.dumps(brief_scenes)}\n"
                          f"Measured problems: {json.dumps(rules)}\n"
                          f'Return {{"scores": {{{", ".join(f"{c!r}: 0-10" for c in CRITERIA[:-1])}}}, "issues": '
                          '[{"criterion", "sceneId", "target": "scene|caption|audio|transition", "severity": '
                          '"major|minor", "problem", "fix"}]}', temperature=0.2)
        c = Critique.model_validate(raw)
        ids = {s["id"] for s in spec["scenes"]}
        scores = {k: scores[k] if k == "visual_quality" else min(scores[k], c.scores[k]) for k in CRITERIA}
        seen = {(i["criterion"], i["sceneId"]) for i in rules}
        issues += [{**i.model_dump(), "source": "model"} for i in c.issues
                   if (i.sceneId in ids or i.sceneId is None) and (i.criterion, i.sceneId) not in seen]
        by = "rules+model"
    except (P.NotConfigured, ValidationError, ValueError):
        pass
    scores = {k: max(0.0, v) for k, v in scores.items()}
    return {"scores": scores, "overall": round(sum(scores.values()) / len(scores), 1), "issues": issues, "by": by}


def weak_scenes(crit: dict) -> list[str]:
    low = {k for k, v in crit["scores"].items() if v < CFG["repair_threshold"]}
    picked = []
    for i in sorted(crit["issues"], key=lambda i: i["severity"] != "major"):
        if i["sceneId"] and (i["severity"] == "major" or i["criterion"] in low) and i["sceneId"] not in picked:
            picked.append(i["sceneId"])
    return picked[:CFG["repair_max_scenes"]]


def revise_scene(spec: dict, sid: str, issues: list[dict], brief: dict, asset_ids) -> dict:
    """Rewrite one scene; timing, id and purpose are locked so the rest of the reel is untouched."""
    s = next(x for x in spec["scenes"] if x["id"] == sid)
    new = dict(s)
    try:
        raw = P.text_json(DIRECTOR, f"Brief: {json.dumps(brief)}\nScene to fix: {json.dumps(s)}\nProblems: "
                          f"{json.dumps(issues)}\nReturn the whole scene JSON with the fixes applied. Keep id, "
                          f"startSeconds, endSeconds and purpose. Voiceover at most {words_budget(s)} words.",
                          temperature=0.5)
        new = Scene.model_validate({**raw, **{k: s[k] for k in ("id", "startSeconds", "endSeconds", "purpose")}},
                                   context={"assets": set(asset_ids)}).model_dump()
    except (P.NotConfigured, ValidationError, ValueError):
        pass
    for i in issues:  # rule fixes always apply, with or without a model
        if i["criterion"] == "hook" and not new["onScreenText"].strip():
            new["onScreenText"] = spec["hook"]["onScreenText"]
            new["voiceover"] = new["voiceover"] or spec["hook"]["spokenText"]
        if i["criterion"] == "cta_clarity":
            spec["callToAction"]["onScreenText"] = spec["callToAction"]["onScreenText"] or brief.get("cta", "")[:32]
            new["onScreenText"] = new["onScreenText"] or spec["callToAction"]["onScreenText"]
        if i.get("maxWords"):  # measured overrun: guarantee the fit even if the model's rewrite didn't
            new["voiceover"] = _clip_words(new["voiceover"], i["maxWords"])
    return new


# ---------- 7. visual review: judged from the rendered frames, not the script ----------

def keyframes(mp4: Path, spec: dict) -> list[dict]:
    """Two hook frames plus each scene's midpoint (at most `review_frames`), as small JPEGs."""
    import imageio_ffmpeg
    sc = spec["scenes"]
    picks = [{"sceneId": sc[0]["id"], "label": "hook", "t": 0.5},
             {"sceneId": sc[0]["id"], "label": "hook", "t": max(0.6, sc[0]["endSeconds"] - 0.3)}]
    picks += [{"sceneId": s["id"], "label": s["purpose"], "t": round((s["startSeconds"] + s["endSeconds"]) / 2, 2)}
              for s in sc[1:]]
    picks = picks[:CFG["review_frames"]]
    for f in picks:
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-ss", str(f["t"]), "-i", str(mp4),
                            "-frames:v", "1", "-vf", "scale=360:640", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                           capture_output=True, timeout=60)
        f["jpg"] = r.stdout
    return [f for f in picks if f["jpg"]]


def visual_checks(frames: list[dict], spec: dict, st: dict) -> tuple[list[dict], dict]:
    """Measured, no model: do the scenes actually look different, and is there any real imagery at all?"""
    import io
    import numpy as np
    from PIL import Image
    mids = {}
    for f in frames:  # one frame per scene (the later hook frame stands for scene 1)
        mids[f["sceneId"]] = np.asarray(Image.open(io.BytesIO(f["jpg"])).convert("RGB").resize((36, 64)), float) / 255
    a = list(mids.values())
    pairs = [np.abs(a[i] - a[j]).mean() for i in range(len(a)) for j in range(i + 1, len(a))]
    variety = float(np.mean(pairs)) if pairs else 0.0
    kinds = [(st.get(s["id"], {}).get("asset") or {}).get("kind") for s in spec["scenes"]]
    real = sum(k in ("image", "video") for k in kinds) / max(1, len(kinds))
    out = []
    if variety < CFG["visual_variety_min"]:
        out.append({"criterion": "visual_quality", "sceneId": None, "target": "scene", "severity": "major",
                    "problem": f"scenes look alike (visual variety {variety:.2f} < {CFG['visual_variety_min']})",
                    "fix": "give each scene its own image, footage or layout", "source": "measured"})
    if real < CFG["real_imagery_min"]:
        out.append({"criterion": "visual_quality", "sceneId": None, "target": "scene",
                    "severity": "major" if real == 0 else "minor",
                    "problem": f"only {real:.0%} of scenes show real photos or footage", "source": "measured",
                    "fix": "upload product/lifestyle shots or connect an image model"})
    return out, {"variety": round(variety, 3), "real_imagery": round(real, 2)}


JUDGE = ("You are a blunt short-form video critic and, at the same time, a 20-year-old who scrolls Instagram for "
         "hours. You get frames from one vertical Reel, in order, plus its script. Judge only what is visible and "
         "said. Anchors: 10 = indistinguishable from a top brand's Reel shot with real footage; 7 = a good "
         "creator-made Reel; 5 = an obvious template or slideshow; 3 = amateur, repetitive or hard to read; "
         "1 = broken. Most AI-made Reels land between 3 and 6. Politeness ruins this review.")


def tile(frames: list[dict], max_images: int) -> tuple[list[bytes], int]:
    """Some vision endpoints cap images per request (Llama 4 on Vertex: 5): put frames side by side to fit."""
    import io
    from PIL import Image
    per = -(-len(frames) // max_images)
    if per <= 1:
        return [f["jpg"] for f in frames], 1
    out = []
    for i in range(0, len(frames), per):
        ims = [Image.open(io.BytesIO(f["jpg"])).convert("RGB") for f in frames[i:i + per]]
        sheet = Image.new("RGB", (sum(x.width for x in ims), max(x.height for x in ims)))
        x = 0
        for im in ims:
            sheet.paste(im, (x, 0))
            x += im.width
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=85)
        out.append(buf.getvalue())
    return out, per


def judge_frames(frames: list[dict], spec: dict, brief: dict, temperature: float = 0.2) -> dict:
    """Blind visual judgement: the judge never sees our scores, the variant name or the maker's notes."""
    shots = "\n".join(f"Frame {i + 1}: {f['sceneId']} ({f['label']}) at {f['t']}s" for i, f in enumerate(frames))
    images, per = tile(frames, CFG["vision_max_images"])
    if per > 1:
        shots += f"\n(Frames are tiled {per} per image, left to right, in frame order.)"
    script = "\n".join(f"{s['id']} {s['startSeconds']}-{s['endSeconds']}s VO: {s['voiceover']} | text: "
                       f"{s['onScreenText']}" for s in spec["scenes"])
    raw = P.vision_json(
        JUDGE, f"Product: {brief.get('product')}\nAudience: {brief.get('audience')}\nPlatform: {spec['platform']}\n"
        f"{shots}\nScript:\n{script}\n"
        f'Return {{"scores": {{{", ".join(f"{c!r}: 0-10" for c in VISUAL)}}}, "stopScroll": 0-10 (would you stop '
        'scrolling in the first 2 seconds), "verdict": str (one blunt sentence), "issues": [{"sceneId", '
        '"criterion", "severity": "major|minor", "problem", "fix"}], "seen": str (second by second, what a '
        'scroller actually sees and how it looks and feels, honestly, including if it looks cheap; plain words, '
        'no scores), "couldBe": str (the same Reel, same script and product, with its visual problems fixed: '
        'what a scroller would see instead, second by second), "couldBeScore": 0-10 (your score for that fixed '
        'version)}',
        images, temperature)
    scores = {c: max(0.0, min(10.0, float(v))) for c, v in (raw.get("scores") or {}).items() if c in VISUAL}
    ids = {s["id"] for s in spec["scenes"]}
    issues = []
    for i in raw.get("issues") or []:
        try:
            x = Issue.model_validate(i)
        except ValidationError:
            continue
        if x.sceneId in ids or x.sceneId is None:
            issues.append({**x.model_dump(), "source": "vision"})
    return {"scores": scores, "stopScroll": float(raw.get("stopScroll") or 0), "verdict": str(raw.get("verdict", ""))[:300],
            "issues": issues, "seen": str(raw.get("seen") or "")[:2000], "couldBe": str(raw.get("couldBe") or "")[:2000],
            "couldBeScore": max(0.0, min(10.0, float(raw.get("couldBeScore") or 0)))}


def visual_review(spec: dict, brief: dict, st: dict, mp4: Path) -> dict:
    frames = keyframes(mp4, spec)
    issues, stats = visual_checks(frames, spec, st)
    scores = {"visual_quality": 8.0}
    for i in issues:
        scores["visual_quality"] -= 3 if i["severity"] == "major" else 1
    out = {"scores": scores, "issues": issues, "stats": stats, "by": "measured"}
    try:
        j = judge_frames(frames, spec, brief)
        out["scores"] = {c: min(scores.get(c, 10.0), j["scores"].get(c, 10.0)) for c in set(scores) | set(j["scores"])}
        out.update(stopScroll=j["stopScroll"], verdict=j["verdict"], issues=issues + j["issues"], seen=j["seen"],
                   couldBe=j["couldBe"], couldBeScore=j["couldBeScore"],
                   by="measured+" + P.available()["vision"])
    except (P.NotConfigured, ValueError, KeyError) as e:
        out["note"] = f"frames not judged by a model: {str(e)[:160]}"
    out["scores"] = {k: round(max(0.0, v), 1) for k, v in out["scores"].items()}
    return out


def merge_visual(crit: dict, vis: dict) -> dict:
    scores = {k: min(v, vis["scores"].get(k, 10.0)) for k, v in crit["scores"].items()}
    return {**crit, "scores": scores, "overall": round(sum(scores.values()) / len(scores), 1),
            "issues": crit["issues"] + vis["issues"], "visual": {k: v for k, v in vis.items() if k != "issues"}}


# ---------- pipeline ----------

_running: set[str] = set()
_lock = threading.Lock()


def claim(reel_id) -> bool:
    with _lock:
        if reel_id in _running:
            return False
        _running.add(reel_id)
        return True


def release(reel_id):
    with _lock:
        _running.discard(reel_id)


def _log(con, reel_id, msg):
    r = load(con, reel_id)
    log = (r.get("log") or [])[-40:] + [{"t": time.time(), "msg": msg}]
    save(con, reel_id, log=log)


def create(con, ad_id: str, brief: dict) -> str:
    rid = "reel-" + uuid.uuid4().hex[:8]
    con.execute("INSERT INTO reels (id, ad_id, status, stage, brief, updated) VALUES (?,?,?,?,?,?)",
                (rid, ad_id, "draft", None, json.dumps(brief), time.time()))
    con.commit()
    folder(rid)
    return rid


def add_asset(con, reel_id: str, role: str, filename: str, data: bytes, note: str = "") -> dict:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    name = safe_name(filename)
    ext = Path(name).suffix
    kind = next((k for k, exts in KINDS.items() if ext in exts), None)
    if not kind:
        raise ValueError(f"unsupported file type '{ext}'; use {sorted(set().union(*KINDS.values()))}")
    if len(data) > CFG["upload_max_mb"] * 1e6:
        raise ValueError(f"file larger than {CFG['upload_max_mb']} MB")
    if kind == "image":
        from PIL import Image
        import io
        Image.open(io.BytesIO(data)).verify()  # rejects non-images with an image extension
    aid = "asset-" + uuid.uuid4().hex[:6]
    path = folder(reel_id) / f"{aid}-{name}"
    path.write_bytes(data)
    a = {"id": aid, "reel_id": reel_id, "role": role, "kind": kind, "name": name, "path": str(path),
         "meta": {"note": note[:300]}}
    con.execute("INSERT INTO reel_assets (id, reel_id, role, kind, name, path, meta) VALUES (?,?,?,?,?,?,?)",
                (aid, reel_id, role, kind, name, str(path), json.dumps(a["meta"])))
    con.commit()
    return a


def set_spec(con, reel_id: str, spec: dict):
    """Validate + finalize + store. Scenes that disappeared lose their state."""
    r = load(con, reel_id)
    al = assets(con, reel_id)
    spec = finalize(validate(spec, [a["id"] for a in al]).model_dump(), r["brief"], al)
    ids = [s["id"] for s in spec["scenes"]]
    con.execute(f"DELETE FROM reel_scenes WHERE reel_id=? AND scene_id NOT IN ({','.join('?' * len(ids))})",
                (reel_id, *ids))
    for sid in ids:
        save_scene(con, reel_id, sid)
    save(con, reel_id, spec=spec)
    return spec


def storyboard(con, reel_id: str):
    try:
        save(con, reel_id, status="planning", stage="storyboard", error=None)
        r = load(con, reel_id)
        spec, by = direct(r["brief"], assets(con, reel_id))
        set_spec(con, reel_id, spec)
        save(con, reel_id, status="storyboard", stage=None, critic=None, renders={})
        _log(con, reel_id, f"storyboard by {by}")
    except Exception as e:
        save(con, reel_id, status="failed", stage=None, error=f"{type(e).__name__}: {str(e)[:400]}")
        raise
    finally:
        release(reel_id)


def update_scene(con, reel_id: str, sid: str, fields: dict):
    r = load(con, reel_id)
    spec = r["spec"]
    for s in spec["scenes"]:
        if s["id"] == sid:
            s.update({k: v for k, v in fields.items() if k not in ("id", "startSeconds", "endSeconds")})
            break
    else:
        raise KeyError(sid)
    return set_spec(con, reel_id, spec)


def regenerate(con, reel_id: str, sid: str):
    """New take of one scene: bumps its nonce so the content-addressed cache makes a fresh one."""
    st = scene_state(con, reel_id).get(sid)
    if st is None:
        raise KeyError(sid)
    save_scene(con, reel_id, sid, regen=(st.get("regen") or 0) + 1, status="pending", error=None)


def replace(con, reel_id: str, sid: str, asset_id: str):
    save_scene(con, reel_id, sid, replaced=asset_id, status="pending", error=None)


def produce(con, reel_id: str):
    """assets -> voice -> captions -> critic (+repair, capped) -> preview. Resumable: done work is skipped by hash."""
    try:
        r = load(con, reel_id)
        if not r.get("spec"):
            raise ValueError("make a storyboard first")
        seed = reel_id
        spec, brief = r["spec"], r["brief"]
        al = assets(con, reel_id)
        save(con, reel_id, status="producing", error=None)
        for stage in ("assets", "voice", "captions"):
            save(con, reel_id, stage=stage)
            {"assets": lambda: stage_assets(con, reel_id, spec, al), "voice": lambda: stage_voice(con, reel_id, spec, brief),
             "captions": lambda: stage_captions(con, reel_id, spec)}[stage]()
        save(con, reel_id, stage="critic")
        history = []
        crit = critique(spec, scene_state(con, reel_id), brief, al)
        for rnd in range(CFG["critic_rounds"]):
            weak = weak_scenes(crit)
            if not weak:
                break
            for sid in weak:
                issues = [i for i in crit["issues"] if i["sceneId"] == sid]
                new = revise_scene(spec, sid, issues, brief, [a["id"] for a in al])
                spec["scenes"] = [new if s["id"] == sid else s for s in spec["scenes"]]
            spec = set_spec(con, reel_id, spec)
            history.append({"round": rnd + 1, "repaired": weak, "before": crit["overall"]})
            _log(con, reel_id, f"critic round {rnd + 1}: repaired {', '.join(weak)}")
            stage_assets(con, reel_id, spec, al)  # hashes: only the revised scenes re-make anything
            stage_voice(con, reel_id, spec, brief)
            stage_captions(con, reel_id, spec)
            crit = critique(spec, scene_state(con, reel_id), brief, al)
        save(con, reel_id, critic={**crit, "history": history}, stage="preview")
        out = folder(reel_id) / "preview.mp4"
        compose(timeline(spec, brief, scene_state(con, reel_id), al, True, seed), out)
        save(con, reel_id, stage="review")
        crit = merge_visual(crit, visual_review(spec, brief, scene_state(con, reel_id), out))
        save(con, reel_id, critic={**crit, "history": history})
        renders = {**(load(con, reel_id).get("renders") or {}), "preview": out.name, "preview_at": time.time()}
        renders.pop("final", None)  # a changed reel invalidates the old export
        save(con, reel_id, status="produced", stage=None, renders=renders)
        _log(con, reel_id, "preview rendered")
    except Exception as e:
        save(con, reel_id, status="failed", error=f"{type(e).__name__}: {str(e)[:400]}")
        raise
    finally:
        release(reel_id)


def export(con, reel_id: str):
    try:
        r = load(con, reel_id)
        save(con, reel_id, status="exporting", stage="final", error=None)
        out = folder(reel_id) / "final.mp4"
        compose(timeline(r["spec"], r["brief"], scene_state(con, reel_id), assets(con, reel_id), False, reel_id), out)
        save(con, reel_id, status="done", stage=None, renders={**(r.get("renders") or {}), "final": out.name})
        _log(con, reel_id, "final exported")
    except Exception as e:
        save(con, reel_id, status="failed", error=f"{type(e).__name__}: {str(e)[:400]}")
        raise
    finally:
        release(reel_id)


def interrupted(con):
    """After a restart, runs that were mid-flight are resumable, not stuck."""
    con.execute("UPDATE reels SET status='interrupted', error='The server restarted during this run. Press Resume; "
                "finished scenes are kept.' WHERE status IN ('planning','producing','exporting')")
    con.commit()
