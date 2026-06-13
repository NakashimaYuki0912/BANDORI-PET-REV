# 回滚脚本：还原多屏 DPI 适配修复 (round 2 — 物理像素一致 & round-trip drift 修复)
# 用法：右键 -> 使用 PowerShell 运行，或在终端中执行：
#   powershell -File "D:\VS_program\BANDORI-PET-REV\.backup_multimon_fix_20260611\rollback.ps1"

$ErrorActionPreference = "Stop"
$backup = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Split-Path -Parent $backup

Write-Host "正在回滚 BANDORI-PET-REV 多屏 DPI 修复 (2026-06-11 round 2) ..." -ForegroundColor Yellow

$files = @("main.py", "pet_process.py", "pet_window.py", "live2d_widget.py", "chat_window.py", "compact_ai_window.py")
foreach ($f in $files) {
    if (Test-Path "$backup\$f") {
        Copy-Item "$backup\$f" "$target\$f" -Force
        Write-Host "  已还原: $f" -ForegroundColor Green
    } else {
        Write-Host "  跳过 (备份不存在): $f" -ForegroundColor Gray
    }
}

Write-Host "回滚完成！" -ForegroundColor Green
