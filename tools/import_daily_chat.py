"""Import the 40-character daily chat text file into greetings.json files."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
from collections.abc import Mapping


CHARACTER_NAME_TO_KEY = {
    "户山香澄": "kasumi",
    "花园多惠": "tae",
    "牛込里美": "rimi",
    "山吹沙绫": "saaya",
    "市谷有咲": "arisa",
    "美竹兰": "ran",
    "青叶摩卡": "moca",
    "上原绯玛丽": "himari",
    "宇田川巴": "tomoe",
    "羽泽鸫": "tsugumi",
    "丸山彩": "aya",
    "冰川日菜": "hina",
    "白鹭千圣": "chisato",
    "大和麻弥": "maya",
    "若宫伊芙": "eve",
    "凑友希那": "yukina",
    "冰川纱夜": "sayo",
    "今井莉莎": "lisa",
    "宇田川亚子": "ako",
    "白金燐子": "rinko",
    "弦卷心": "kokoro",
    "濑田薰": "kaoru",
    "北泽育美": "hagumi",
    "松原花音": "kanon",
    "奥泽美咲": "misaki",
    "仓田真白": "mashiro",
    "桐谷透子": "touko",
    "广町七深": "nanami",
    "二叶筑紫": "tsukushi",
    "八潮瑠唯": "rui",
    "和奏瑞依": "rei",
    "朝日六花": "lock",
    "佐藤益木": "masuki",
    "鳰原令王那": "pareo",
    "珠手知由": "chu2",
    "高松灯": "tomorin",
    "千早爱音": "anon",
    "要乐奈": "rana",
    "长崎素世": "soyo",
    "椎名立希": "taki",
}

_HEADER_RE = re.compile(r"^【([^】]+)】\s*$")
_STAGE_NAME_RE = re.compile(r"\s*[（(][^）)]*[）)]\s*$")
_NAME_ALIASES = {"长崎爽世": "长崎素世"}
_NEUTRAL_MOTION_PREFIXES = ("natural", "smile")
_ACTION_TAG_RE = re.compile(r"\[[^\[\]\r\n]+\]")


def normalize_character_name(value: str) -> str:
    name = _STAGE_NAME_RE.sub("", str(value or "").strip())
    return _NAME_ALIASES.get(name, name)


def parse_daily_chat_source(
    source: pathlib.Path,
    *,
    name_to_key: Mapping[str, str] = CHARACTER_NAME_TO_KEY,
) -> dict[str, list[str]]:
    """Parse and strictly validate the source text by character heading."""
    expected_keys = set(name_to_key.values())
    parsed: dict[str, list[str]] = {}
    current_key: str | None = None

    for line_number, raw_line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        header = _HEADER_RE.fullmatch(line)
        if header:
            name = normalize_character_name(header.group(1))
            key = name_to_key.get(name)
            if not key:
                raise ValueError(
                    f"Unknown character heading at line {line_number}: {header.group(1)}"
                )
            if key in parsed:
                raise ValueError(f"Duplicate character heading for {key}")
            parsed[key] = []
            current_key = key
            continue

        if line and set(line) == {"="}:
            current_key = None
            continue
        if current_key and line:
            parsed[current_key].append(line)

    missing = expected_keys - set(parsed)
    extra = set(parsed) - expected_keys
    if missing or extra:
        raise ValueError(
            f"Character coverage mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )

    for key, lines in parsed.items():
        if len(lines) != 12:
            raise ValueError(f"{key} must have exactly 12 lines, found {len(lines)}")
        if len(set(lines)) != 12:
            raise ValueError(f"{key} contains duplicate daily chat lines")
        if any(_ACTION_TAG_RE.search(line) for line in lines):
            raise ValueError(f"{key} contains an action tag in daily chat text")
    return parsed


def build_daily_chat_entries(
    greetings: dict,
    lines: list[str],
) -> list[dict[str, str]]:
    """Bind source lines to existing neutral motions without changing old data."""
    if len(lines) != 12:
        raise ValueError("daily chat requires exactly 12 lines")

    neutral_actions: list[dict[str, str]] = []
    for response in greetings.get("click_responses", []) or []:
        if not isinstance(response, dict):
            continue
        motion_value = response.get("motion", "")
        expression_value = response.get("expression", "")
        motion = motion_value.strip() if isinstance(motion_value, str) else ""
        expression = (
            expression_value.strip()
            if isinstance(expression_value, str)
            else ""
        )
        action = {"motion": motion, "expression": expression}
        if motion.lower().startswith(_NEUTRAL_MOTION_PREFIXES):
            neutral_actions.append(action)

    actions = neutral_actions or [{"motion": "", "expression": ""}]
    result: list[dict[str, str]] = []
    for index, text in enumerate(lines):
        action = actions[index % len(actions)]
        entry = {"text": text}
        if action["motion"]:
            entry["motion"] = action["motion"]
        if action["expression"]:
            entry["expression"] = action["expression"]
        result.append(entry)
    return result


def _write_json_atomic(path: pathlib.Path, data: dict) -> None:
    temporary = path.with_name(f".{path.name}.daily-chat.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def sync_daily_chat(
    project_root: pathlib.Path,
    parsed: Mapping[str, list[str]],
    *,
    check: bool = False,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Write or verify the generated daily_chat pools."""
    changed: list[pathlib.Path] = []
    unchanged: list[pathlib.Path] = []
    pending: list[tuple[pathlib.Path, dict, list[dict[str, str]]]] = []
    for key, lines in parsed.items():
        path = project_root / "characters" / key / "greetings.json"
        if not path.is_file():
            raise FileNotFoundError(f"Missing greetings file: {path}")
        greetings = json.loads(path.read_text(encoding="utf-8"))
        expected = build_daily_chat_entries(greetings, list(lines))
        if greetings.get("daily_chat") == expected:
            unchanged.append(path)
            continue
        changed.append(path)
        pending.append((path, greetings, expected))

    if not check:
        for path, greetings, expected in pending:
            greetings["daily_chat"] = expected
            _write_json_atomic(path, greetings)
    return changed, unchanged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import 40-character desktop-pet daily chat text.",
    )
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that generated data is current without writing files.",
    )
    args = parser.parse_args()

    parsed = parse_daily_chat_source(args.source)
    changed, unchanged = sync_daily_chat(
        args.project_root.resolve(),
        parsed,
        check=args.check,
    )
    if args.check and changed:
        print(f"daily chat data is stale in {len(changed)} file(s)")
        return 1
    verb = "verified" if args.check else "updated"
    print(
        f"{verb}: {len(changed) if not args.check else len(unchanged)}; "
        f"unchanged: {len(unchanged)}; characters: {len(parsed)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
