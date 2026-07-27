# ADR-0003: Tune desktop-pet voices at GPT-SoVITS inference time

## Status

Accepted (2026-07-27)

## Context

The project shares GPT-SoVITS v2 weights across desktop-pet dialogue and
greetings. Retraining every voice to make all output slightly slower, or to
give a single character a livelier delivery, is expensive and cannot be
adjusted by users at runtime.

The deployed API already accepts speed and sampling controls. The client used
only the server defaults, so every character used a speed factor of `1.0`.
Cached greeting audio also needs to distinguish inference profiles; otherwise
a changed preset can silently play an older result.

## Decision

Keep the GPT-SoVITS server API unchanged. The client sends a validated
inference profile with every request:

- a user-visible global speed factor, defaulting to `0.92`;
- conservative sampling defaults for new configurations; existing saved
  temperature choices remain unchanged;
- small built-in profiles for Rei (Layer), Lisa, and CHU²;
- optional persisted `tts_character_profiles` overrides for future controls.

The cache key includes all profile values that affect audio generation.

CHU²'s desired high-energy delivery is not represented as a synthetic pitch
control. It should use a same-speaker, energetic reference clip plus its exact
Japanese transcript when that asset is supplied.

## Consequences

- New and existing users can slow all voices from the TTS settings page without
  changing server source or weights.
- Per-character pacing/sampling differences are reproducible and do not reuse
  audio from a different profile.
- Voice emotion remains bounded by the quality and style of the reference
  audio; adding an energetic CHU² reference clip is a separate asset task.
