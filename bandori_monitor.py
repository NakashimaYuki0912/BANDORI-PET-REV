#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BandoriPet Unified Supervisor & Real-time TTS Diagnostics Monitor
=================================================================
1. Process & Study Supervisor:
   - Tracks active foreground window and process.
   - Monitors study focus (allowing Study processes and PotPlayer; alerting on distractions like QQ/WeChat/Games).
2. TTS & BandoriPet Health Diagnostics:
   - Checks backend reachability (Port 9880 / SSH tunnel to server.vanillatte.cafe).
   - Audits config.json TTS & LLM settings (translation schema compatibility, ambient TTS provider).
   - Tails bandori_error.log and settings_error.log in real time to capture speech errors immediately.
   - Diagnoses why any spoken dialogue failed to play voice.
"""

import datetime
import hashlib
import json
import os
import pathlib
import re
import socket
import sys
import time

ROOT_DIR = pathlib.Path(__file__).resolve().parent
LOG_FILE = ROOT_DIR / "bandori_monitor.log"
CONFIG_FILE = ROOT_DIR / "config.json"
BANDORI_ERR_LOG = ROOT_DIR / "bandori_error.log"
SETTINGS_ERR_LOG = ROOT_DIR / "settings_error.log"

_TTS_TRANSLATION_FORMAT_VERSION = "speaker-name-guidance-v1"


def log(msg: str, level: str = "INFO"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def check_port_open(host: str = "127.0.0.1", port: int = 9880, timeout: float = 0.5) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        log(f"加载 config.json 失败: {exc}", "WARN")
    return {}


def audit_tts_configuration(cfg: dict) -> dict:
    issues = []
    tts_enabled = cfg.get("tts_enabled", False)
    current_char = cfg.get("character", "rui")
    ambient_tts = cfg.get("ambient_tts_provider", "off")
    llm_api_url = cfg.get("llm_api_url", "")
    llm_aux_api_url = cfg.get("llm_aux_api_url", "")

    # 1. Port 9880 / Backend check
    port_open = check_port_open("127.0.0.1", 9880)
    if not port_open:
        issues.append(
            "【严重】127.0.0.1:9880 端口离线！本地或远程 GPT-SoVITS 后端未连接，任何未预先缓存的台词或动态对话均无法播放语音。"
        )

    # 2. Ambient TTS setting
    if ambient_tts == "off":
        issues.append(
            "【提示】ambient_tts_provider 设为 'off'，环境感知主动碎碎念不会请求 OpenAI TTS，若同时 9880 离线则主动说话无声。"
        )

    # 3. Translation schema mismatch
    trans_url = (llm_aux_api_url or llm_api_url or "").lower()
    if "responses" in trans_url:
        issues.append(
            "【高危】TTS 翻译使用的是 Responses API 端点 (/responses)，但 tts_manager 发送的是 Chat Completions 协议 (messages:[...])，会导致翻译阶段报 HTTP 400 失败并跳过语音！"
        )

    # 4. Reference audio file
    ref_audio = ROOT_DIR / "audio_reference" / f"{current_char}.mp3"
    if not ref_audio.exists():
        issues.append(f"【缺失】角色 {current_char} 在 audio_reference/ 目录下不存在 {current_char}.mp3。")

    return {
        "tts_enabled": tts_enabled,
        "current_char": current_char,
        "port_open": port_open,
        "ambient_tts": ambient_tts,
        "issues": issues,
    }


class LogTailer:
    def __init__(self, filepath: pathlib.Path):
        self.filepath = filepath
        self.file_pos = 0
        if self.filepath.exists():
            self.file_pos = self.filepath.stat().st_size

    def check_new_lines(self) -> list[str]:
        if not self.filepath.exists():
            return []
        try:
            curr_size = self.filepath.stat().st_size
            if curr_size < self.file_pos:
                self.file_pos = 0
            if curr_size > self.file_pos:
                with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.file_pos)
                    lines = f.readlines()
                    self.file_pos = f.tell()
                    return [line.strip() for line in lines if line.strip()]
        except Exception:
            pass
        return []


def get_foreground_info() -> tuple[str, str, str]:
    """Retrieve foreground process name, window title, and category."""
    try:
        from process_supervisor import get_foreground_process_info
        fg = get_foreground_process_info()
        name = str(fg.get("name", "") or "").strip().lower()
        if name.endswith(".exe"):
            name = name[:-4]
        title = str(fg.get("title", "") or "").strip()
        cat = fg.get("category", "general")
        return name, title, cat
    except Exception:
        return "", "", "general"


def main():
    log("=" * 65)
    log("BandoriPet 进程监督与 TTS 运行监控程序启动")
    log("=" * 65)

    cfg = load_config()
    audit = audit_tts_configuration(cfg)
    log(f"当前监控角色: {audit['current_char']} | TTS 总开关: {audit['tts_enabled']} | 端口 9880 监听: {audit['port_open']}")
    for issue in audit["issues"]:
        log(issue, "WARN")

    log("-" * 65)
    log("【监督模式说明】: 正在监督学习进程与 PotPlayer，切换至违规进程（QQ、微信、游戏等）时将实时警报。")
    log("【TTS 监测说明】: 正在持续监听 TTS 合成请求、错误日志及 9880 服务状态。")
    log("-" * 65)

    bandori_tailer = LogTailer(BANDORI_ERR_LOG)
    settings_tailer = LogTailer(SETTINGS_ERR_LOG)

    last_port_state = audit["port_open"]
    last_fg_app = ""
    last_warn_time = 0.0

    error_patterns = [
        re.compile(r"\[pet tts\]\s*(.*)", re.I),
        re.compile(r"\[ambient proactive\]\s*(.*)", re.I),
        re.compile(r"\[ambient-tts\]\s*(.*)", re.I),
        re.compile(r"\[ssh_tunnel\]\s*(.*)", re.I),
        re.compile(r"\[ProcessMonitor\]\s*(.*)", re.I),
    ]

    # Allowed in study session
    study_allowed = {"potplayer", "potplayermini", "potplayermini64", "code", "devenv", "notepad++", "obsidian", "notion", "windowsterminal", "cmd", "powershell"}

    tick = 0
    try:
        while True:
            time.sleep(1.0)
            tick += 1

            # 1. Log tailing
            for line in bandori_tailer.check_new_lines():
                for pattern in error_patterns:
                    m = pattern.search(line)
                    if m:
                        log(f"[BandoriPet 告警] {line}", "ALERT")
                        break

            for line in settings_tailer.check_new_lines():
                if "error" in line.lower() or "exception" in line.lower():
                    log(f"[设置面板告警] {line}", "WARN")

            # 2. Port status monitoring every 5s
            if tick % 5 == 0:
                is_open = check_port_open("127.0.0.1", 9880)
                if is_open != last_port_state:
                    last_port_state = is_open
                    if is_open:
                        log("TTS 后端服务已连接 (127.0.0.1:9880 在线)", "SUCCESS")
                    else:
                        log("TTS 后端服务断开 (127.0.0.1:9880 离线)，在线语音不可用", "WARN")

            # 3. Process Supervision (Check foreground window) every 2s
            if tick % 2 == 0:
                fg_name, fg_title, fg_cat = get_foreground_info()
                if fg_name and fg_name != last_fg_app:
                    last_fg_app = fg_name
                    # Check if user switched to distraction
                    now = time.monotonic()
                    if fg_cat in ("game", "chat") or fg_name in ("qq", "wechat", "weixin", "wxwork", "discord"):
                        if now - last_warn_time > 10.0:
                            last_warn_time = now
                            log(
                                f"【监督提醒】检测到焦点切换到违规/摸鱼应用: [{fg_name}] '{fg_title}'（分类: {fg_cat}）！请专心学习！",
                                "SUPERVISOR",
                            )
                    elif fg_name in study_allowed or fg_cat == "study" or "potplayer" in fg_name:
                        log(f"【监督确认】当前在前台学习应用: [{fg_name}] '{fg_title}'", "STUDY")

    except KeyboardInterrupt:
        log("监控程序退出")


if __name__ == "__main__":
    main()
