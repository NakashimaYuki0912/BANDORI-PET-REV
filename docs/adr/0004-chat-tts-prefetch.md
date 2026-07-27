# ADR-0004: Prefetch ordered chat TTS while the current sentence plays

## Status

Accepted (2026-07-27)

## Context

Streaming LLM replies are split into sentences so the first sentence can be
spoken as soon as possible. Previously the chat queue used the same sequence
cursor for both request dispatch and playback. It also refused to start a
request while local audio played.

That made every later sentence wait for the prior sentence to finish locally
before remote GPT-SoVITS synthesis even began, producing conspicuous silent
gaps. The existing queue already had ordered audio buffers capable of holding
future sentence audio.

## Decision

Use separate cursors for request and playback order. A sentence request starts
as soon as the prior request slot is available, even while a previous sentence
is playing. Audio still enters the existing buffer and is released strictly in
sequence. The configured request concurrency limit remains enforced.

## Consequences

- Later sentence synthesis overlaps local playback, reducing audible gaps.
- No GPT-SoVITS server change or streaming endpoint is required.
- Playback order and character lip-sync remain deterministic even if a later
  request finishes earlier.
