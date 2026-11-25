"""Story Mode (连续多段微故事) 测试工具

用于测试与验证昨天的 "让 AI 像讲故事一样，连续说几段话" (Ambient Story Mode) 功能。

使用方法:
    python TOOL-test_story_mode.py [--character kasumi] [--offline]

功能:
1. 测试 LLM 微故事 Prompt 构造与多段 JSON 数组解析。
2. 实际调用配置的 LLM API 生成一段连贯微故事。
3. 演示多段连续气泡与动作的实际节奏排队流程。
"""

import argparse
import json
import sys
import time

from config_manager import ConfigManager
from ambient_chat_manager import (
    AmbientPrefetchWorker,
    build_ambient_prompt_bundle,
    gather_desktop_context,
    parse_ambient_story_segments,
)


def run_story_test(character: str = "kasumi", offline: bool = False):
    print("=" * 60)
    print("      BandoriPet - 连续微故事模式 (Story Mode) 测试工具")
    print("=" * 60)

    cfg = ConfigManager()
    char = character.lower().strip() or cfg.get("current_character", "kasumi")

    print(f"\n[1/3] 检查配置与环境:")
    story_enabled = cfg.get("ambient_story_mode_enabled", True)
    story_prob = cfg.get("ambient_story_probability", 0.30)
    api_url = cfg.get("llm_api_url", "")
    model_id = cfg.get("llm_model_id", "gpt-4o-mini")

    print(f"  - 测试角色: {char}")
    print(f"  - 微故事模式开启: {story_enabled}")
    print(f"  - 触发概率: {story_prob * 100:.0f}%")
    print("  - 接续方式：上一段语音播放结束后直接切换到下一段")
    print(f"  - LLM API: {api_url or '(未配置)'}")
    print(f"  - LLM 模型: {model_id}")

    context = gather_desktop_context(cfg)
    prompt, user_cue = build_ambient_prompt_bundle(char, context, cfg, story_mode=True)

    print(f"\n[2/3] 微故事 Prompt 构造预览:")
    print("-" * 50)
    print(f"User Cue: {user_cue}")
    print("-" * 50)
    prompt_snippet = prompt.split("【台词输出要求")[-1]
    print(f"输出规范要求: 【台词输出要求{prompt_snippet[:280]}...")
    print("-" * 50)

    segments = []
    if not offline and api_url and cfg.get("llm_api_key"):
        print(f"\n[3/3] 正在调用 LLM API 生成微故事...")
        worker = AmbientPrefetchWorker(char, cfg, story_mode=True)

        reply_container = []
        worker.fetched.connect(lambda c, entry: reply_container.append(entry))
        worker.start()

        for _ in range(150):
            if not worker.isRunning():
                break
            time.sleep(0.1)

        if reply_container:
            entry = reply_container[0]
            if entry.get("is_story") and entry.get("segments"):
                segments = entry["segments"]
                print("  => 成功从 LLM 获取并解析出连贯微故事！")
            else:
                print(f"  => LLM 返回了单句台词 (Fallback): {entry.get('text')}")
        else:
            print("  => API 调用超时或未返回，使用内置模拟故事数据演示节奏。")

    if not segments:
        print("\n使用模拟的 3 段连贯微故事进行节奏演示:")
        mock_raw = (
            '["今天在练习室看到有咲偷偷把盆栽搬到吉他旁边了呢。[smile01]", '
            '"本来想去打个招呼，结果她一看到我走过来，脸唰地一下就红了！[surprised01]", '
            '"诶嘿嘿~傲娇的有咲今天也超级可爱！[smile02]"]'
        )
        segments = parse_ambient_story_segments(mock_raw)

    print(f"\n解析出的多段微故事 (共 {len(segments)} 段):")
    for i, seg in enumerate(segments, 1):
        print(f"  [第 {i} 段] 动作: [{seg.get('motion', '无')}] | 文本: {seg.get('text')}")

    print("\n" + "=" * 60)
    print("      模拟在桌宠上的讲故事连贯投递效果演示")
    print("=" * 60)

    for i, seg in enumerate(segments, 1):
        text = seg.get("text", "")
        motion = seg.get("motion", "")
        print(f"\n▶ 弹出第 {i}/{len(segments)} 段气泡:")
        print(f"   💬 台词: \"{text}\"")
        if motion:
            print(f"   💃 Live2D 动作触发: [{motion}]")
        print(f"   ⏱️ 气泡展示中 (打字机效果 & 语音播放)...")

        # 模拟当前段的播放时间。
        time.sleep(1.8)
        print("   ✓ 语音播放完毕")

    print("\n" + "=" * 60)
    print("  测试完成！整个连贯微故事已完整讲完。")
    print("=" * 60)
    print("\n要实测桌宠播放，可从托盘或环形菜单点「讲故事」。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BandoriPet Story Mode Test Tool")
    parser.add_argument("--character", type=str, default="kasumi", help="测试角色 (如 kasumi, arisa, yukina)")
    parser.add_argument("--offline", action="store_true", help="不调用外部 API，直接模拟演示")
    args = parser.parse_args()

    run_story_test(character=args.character, offline=args.offline)
