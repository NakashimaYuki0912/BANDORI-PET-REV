# -*- coding: utf-8 -*-
"""
TOOL-check-tts-status.py
BandoriPet 本地 GPT-SoVITS 状态诊断与自检工具
"""

import json
import sys
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path

def main():
    print("=" * 60)
    print("      BandoriPet 本地 GPT-SoVITS 状态诊断工具")
    print("=" * 60)

    # 1. 检查 config.json
    project = Path(__file__).resolve().parent
    cfg_path = project / "config.json"
    if not cfg_path.exists():
        print("[X] 错误: 未找到 config.json 配置文件！")
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        print("[OK] 读取 config.json 成功")
    except Exception as e:
        print(f"[X] 解析 config.json 失败: {e}")
        return

    tts_enabled = cfg.get("tts_enabled", False)
    api_url = cfg.get("tts_api_url", "http://127.0.0.1:9880/")
    weights_root = cfg.get("tts_gpt_sovits_root", "D:/BANDORI-GPT-SoVITS")
    print(f" - TTS 状态开关: {'[已启用]' if tts_enabled else '[未启用]'}")
    print(f" - TTS API 端口: {api_url}")
    print(f" - 权重根目录:   {weights_root}")

    # 2. 检查权重目录与文件
    root_path = Path(weights_root)
    ckpt_dir = root_path / "weights" / "ckpt_files"
    pth_dir = root_path / "weights" / "pth_files"
    wh_ckpt_dir = root_path / "weights" / "warehouse" / "ckpt_files"
    wh_pth_dir = root_path / "weights" / "warehouse" / "pth_files"

    if ckpt_dir.exists() and pth_dir.exists():
        active_ckpts = list(ckpt_dir.glob("*.ckpt"))
        active_pths = list(pth_dir.glob("*.pth"))
        wh_ckpts = list(wh_ckpt_dir.glob("*.ckpt")) if wh_ckpt_dir.exists() else []
        wh_pths = list(wh_pth_dir.glob("*.pth")) if wh_pth_dir.exists() else []

        print(f"\n[OK] 模型目录结构正常:")
        print(f" - 主力激活模型: CKPT {len(active_ckpts)} 个, PTH {len(active_pths)} 个 (覆盖角色: {len(active_ckpts)})")
        print(f" - 仓库备选模型: CKPT {len(wh_ckpts)} 个, PTH {len(wh_pths)} 个")
    else:
        print(f"\n[!] 警告: 未在 {weights_root} 找到标准 weights 目录")

    # 3. 检查本地参考音频与台词
    ref_dir = project / "audio_reference"
    dialog_path = ref_dir / "dialog.json"
    if ref_dir.exists() and dialog_path.exists():
        audios = list(ref_dir.glob("*.mp3")) + list(ref_dir.glob("*.wav"))
        print(f"[OK] 内置参考音频正常: 共 {len(audios)} 个声优音频切片, 包含 dialog.json 黄金台词")
    else:
        print(f"[X] 错误: audio_reference 目录不完整")

    # 4. 测试本地 GPT-SoVITS 服务端联通性
    print(f"\n[?] 正在检测 GPT-SoVITS API 服务端 ({api_url})...")
    is_online = False
    try:
        host = urlsplit(api_url).hostname
        opener = (
            urllib.request.build_opener(urllib.request.ProxyHandler({}))
            if host in {"127.0.0.1", "localhost", "::1"}
            else urllib.request.build_opener()
        )
        with opener.open(api_url.rstrip("/") + "/openapi.json", timeout=4) as resp:
            routes = json.load(resp).get("paths", {})
        required = {"/tts", "/set_gpt_weights", "/set_sovits_weights"}
        is_online = required <= routes.keys()
    except (OSError, ValueError) as exc:
        print(f" >>> [OFFLINE] 无法读取 GPT-SoVITS API: {exc}")

    if is_online:
        print(" >>> [ONLINE] GPT-SoVITS API 路由已就绪。")
    else:
        print(" >>> 需要本机服务时请运行 TOOL-start-gpt-sovits.bat。")

    print("\n" + "=" * 60)
    return 0 if is_online else 1

if __name__ == "__main__":
    sys.exit(main())
