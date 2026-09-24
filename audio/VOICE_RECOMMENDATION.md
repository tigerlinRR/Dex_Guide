# Narration Voice — Recommendation

For the Dex office-tour narration (4 stops, English, friendly + professional + clear).
Final scripts are in `audio/scripts/`. Total is ~230 words (~1,400 characters) — small,
so any service's free tier covers it easily.

## Character to aim for
Dex is a friendly robot guide that introduces itself ("I'm Dex"). Pick a voice that is
**warm, clear, and lightly upbeat** — not a flat "documentary narrator." Clear
enunciation matters (visitors, possibly a noisy demo room).

## Top pick — ElevenLabs (best quality, customer-facing)
- Default voice: **Rachel** (warm, clear American female — the most reliable narration voice).
- Male alternative: **Adam** (confident, clear). Or try a warmer male from the Voice Library.
- Model: **Eleven Multilingual v2** (or the newest v3 if offered).
- Settings: Stability ~45–55, Similarity ~80, Style ~15–30 (a little warmth),
  Speaker Boost ON. Speed slightly slow (~0.9–0.95) for a tour.
- How (no coding, ~5 min): elevenlabs.io → Voice Library → pick the voice →
  Text-to-Speech → paste each of the 4 scripts → Generate → Download MP3.
  Free tier (~10k chars/month) covers all 4 clips.

## Easy/cheap alternative — OpenAI TTS (very natural, one API call)
- Voice: **Nova** (bright, energetic — good for an upbeat guide) or **Fable**
  (warm, expressive, slight British charm).
- Model: `gpt-4o-mini-tts` or `tts-1-hd`.
- Needs an API key. If you have one, Claude can script the generation for all 4 clips.

## Others (all fine, not necessary): Azure Neural (Aria/Jenny/Guy), Google Neural2,
PlayHT, Murf.

## Suggested next step tomorrow
Generate a short sample of the Welcome script with 2 voices (e.g., ElevenLabs Rachel vs.
a male), compare, then produce all 4 in the chosen voice. Name them
`01_welcome` `02_demo` `03_sales` `04_tech`, drop into `audio/`, and Claude wires them
to the stops and pushes to the robot.
