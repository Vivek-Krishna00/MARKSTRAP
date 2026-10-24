# Reel Director

Turns an approved concept into a vertical 9:16 MP4: brief → validated storyboard → visuals, voice, captions →
critic with targeted repair → preview → 1080×1920 export. Everything inside is open source (hackathon rule), so the
composer is MoviePy + ffmpeg, not Remotion (source-available licence).

## Use it
1. `/app` → approve a concept → **Create Reel** (on the concept card or in the launch pack).
2. The brief is pre-filled from the concept, the campaign brief and constraints (hex colours in brand rules become
   the palette). Adjust platform, seconds (6–90), CTA, style.
3. Drop references with a role: product, character, location, style, logo, music, font, reference Reel. Add a note
   for what must stay the same ("pink moon sticker"); it is inherited by every scene that uses that reference.
4. **Generate storyboard**. Edit any scene (voiceover, on-screen text, visual source, references) before anything is
   generated. Each edit is validated and re-composes the scene's generation prompt.
5. **Produce Reel**: assets → voice → captions → critic (+ one repair round) → low-res preview.
6. Per scene: **Regenerate scene** (new take, only that scene) or **Replace with my media**.
7. **Export final MP4** → **Download MP4**.

No paid provider: `make reel-demo` (add `FINAL=1` for 1080p) renders the fixture `engine/data/reel_demo.json` into
`data/reels/<id>/`; the UI works the same with `REEL_TEXT_PROVIDER=mock`.

## Setup
- `make setup` installs MoviePy and Pillow; ffmpeg comes bundled via `imageio-ffmpeg` (no system install).
- `make reel-setup` installs Piper TTS and downloads `en_US-lessac-medium` (~60 MB) into `data/voices/`.
  Without it the voice track is silent and captions are timed at the `reel.wpm` dial.
- Optional word timings from the audio: `pip install faster-whisper` and `REEL_TIMING_PROVIDER=whisper`.

## Providers (`REEL_<KIND>_PROVIDER`; the side panel shows what is live)
| kind | real | without it |
|---|---|---|
| text | `engine/llm.py` (open model; `LLM_PROVIDER`/`LLM_BASE_URL`) | template storyboard + rule-based critic (`mock`) |
| image | `IMAGE_BASE_URL` (open-weight, OpenAI-compatible; e.g. FLUX.1-schnell) | assigned upload, else motion graphics |
| video | none yet: no open video model host (Wan 2.x / LTX-Video would plug into `reel_providers.video`) | still + Ken Burns |
| tts | Piper | silent clip |
| timing | faster-whisper | per-word share of each scene's clip |
| music | your upload (role = music) | procedural pad, generated, no licence to track |
| stock | `openverse` (CC images, attribution stored on the asset) | off |

Sora and other proprietary APIs are deliberately absent (hackathon rule, and no API access).

## How it holds together
- **Schema**: `reel.ReelSpec` (pydantic). Contiguous timing that sums to the duration, a hook that ends by 3 s, enum
  purposes and asset types, reference ids that exist. The model gets one re-ask with the validation error, then
  the template director takes over: the flow never blocks.
- **Prompts**: the director fills structured fields; `scene_prompt` assembles subject, action, environment,
  composition, camera, movement, lighting, style, palette, tone, duration, 9:16, motion, product placement,
  references, continuity and exclusions in Python, so none can go missing.
- **Continuity profile**: spec continuity + brand palette/type + a "keep" rule per reference role; every scene inherits it.
- **Resumable, no double spend**: each scene stores status, error, attempts and the hash of what its visual and
  voice were made from. A run skips scenes whose hash is unchanged; generations are content-addressed in
  `data/reels/cache/`. A server restart marks running reels *interrupted*; **Resume** continues.
- **Critic**: measured checks (voice overrun from the real audio length, text length, hook, CTA, failed or stand-in
  visuals) plus model scores on 11 criteria (minimum of both wins). Weak scenes are rewritten with timing locked;
  only their hashes change, so only they are re-made. Capped by `reel.critic_rounds` and `reel.repair_max_scenes`.
- **Composer**: `engine/compose.py` draws `reel.timeline()` only: Ken Burns stills, video, motion graphics,
  crossfade/slide/whip, word-highlight captions in the safe zones, per-scene voice, music ducked under the voice,
  whoosh/pop SFX, logo + CTA end card. Renders in a subprocess with a timeout.
- Dials: `config.yaml` → `reel:`.

## Limits
- No auth in the app (none exists yet); anyone who can reach the server can make reels.
- Reels live in the campaign DB; starting a new campaign archives them with it (files stay in `data/reels/`).
- Reference images guide the image model through the prompt only (the OpenAI images API takes no image input).
- Reference Reels are stored and named to the director but not analysed (no open vision model wired in).
- Measured on an M-series Mac: 20 s preview ≈ 5 s, 1080p export ≈ 13 s; storyboard on DeepSeek V4.1 Flash ≈ 16 s.

## Licences
MoviePy MIT · ffmpeg LGPL/GPL (bundled by imageio-ffmpeg) · Pillow MIT-CMU · Piper GPL-3.0 (voices MIT) ·
faster-whisper MIT · Manrope OFL (`engine/data/fonts/OFL.txt`) · Openverse media under CC (attribution kept).
