---
name: bandori-character
description: >-
  Use this skill when adding a new BanG Dream! character to BandoriPet, 
  managing existing character data, or auditing character completeness. 
  Covers System Prompt creation, PROMPT.md/OUTFIT.md updates, model directory 
  validation, audio reference checks, and greetings.json setup.
---

# BandoriPet Character Management

Standard procedure for adding or managing BanG Dream! characters in BandoriPet.

## Character Key Convention

- Use **lowercase English** name as the key (e.g., `kasumi`, `anon`, `tomorin`)
- The key determines directory names across the entire project
- Chinese name directories also exist for user-friendliness but the **English key is canonical**

## Adding a New Character — Checklist

### 1. Create Character System Prompt

Create `characters/<key>/greetings.json`:

```json
{
  "<key>": {
    "morning": ["早上好的问候语1", "早上好的问候语2"],
    "afternoon": ["下午好的问候语1"],
    "evening": ["晚上好的问候语1"],
    "night": ["晚安的问候语1"],
    "default": ["默认问候语1"]
  }
}
```

The LLM System Prompt for each character is typically located in `characters/<key>/` 
or composed dynamically by `chat_process.py`. Check `chat_process.py` for the 
current prompt assembly logic.

### 2. Update PROMPT.md

Edit [PROMPT.md](../../PROMPT.md) at the project root:
- Add the character's action tags section
- Follow existing format patterns exactly
- Action tags use `[tagname]` format — **never** use `（）` or `*` for actions

### 3. Update OUTFIT.md

Edit [OUTFIT.md](../../OUTFIT.md) at the project root:
- Add all available outfits/costumes for the character
- Follow the existing table format

### 4. Verify Model Directory

Check that `models/<key>/` exists (directory or `.zst` archive):
- For directory format: must contain the Live2D model files
- For zst format: `models/<key>.zst` processed by `zst_model_archive.py`

### 5. Audio Reference (Optional)

If TTS voice cloning is desired:
- Place a reference audio sample in `audio_reference/`
- File naming: typically `<key>_ref.wav` or similar
- Japanese voice samples preferred for BanG Dream! characters

## Validation Script

Run these checks to verify character completeness:

```python
# Quick validation — run from project root
import os, json

key = "NEW_CHARACTER_KEY"

checks = {
    "greetings.json": os.path.exists(f"characters/{key}/greetings.json"),
    "model_dir_or_zst": os.path.isdir(f"models/{key}") or os.path.exists(f"models/{key}.zst"),
    "PROMPT.md mentions": key in open("PROMPT.md", encoding="utf-8").read(),
    "OUTFIT.md mentions": key in open("OUTFIT.md", encoding="utf-8").read(),
}

for check, passed in checks.items():
    print(f"{'✅' if passed else '❌'} {check}")
```

## Existing Characters Reference

As of v3.1.0.2, the project has **81 character directories** (40 English-keyed + 41 Chinese-named) 
in `characters/`. Core English keys include:

`ako`, `anon`, `arisa`, `aya`, `chisato`, `chu2`, `eve`, `hagumi`, `himari`, 
`hina`, `kanon`, `kaoru`, `kasumi`, `kokoro`, `lisa`, `lock`, `mashiro`, 
`masuki`, `maya`, `misaki`, `moca`, `nanami`, `pareo`, `ran`, `rana`, `rei`, 
`rimi`, `rinko`, `rui`, `saaya`, `sayo`, `soyo`, `tae`, `taki`, `tomoe`, 
`tomorin`, `touko`, `tsugumi`, `tsukushi`, `yukina`

## Important Notes

- Character model **copyright belongs to original rights holders** — no commercial use
- The `band.json` file at project root contains band/character metadata
- `outfit.json` contains structured outfit data alongside `OUTFIT.md`
