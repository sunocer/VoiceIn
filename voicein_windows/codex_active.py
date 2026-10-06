import base64
import subprocess
import sys

from .codex_tasks import discover_codex_tasks


_PS_SCRIPT = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$p=Get-Process ChatGPT | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1
if(-not $p){exit 3}
$root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$condition=New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Document)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'RootWebArea'))
)
$doc=$root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
if(-not $doc -or -not $doc.Current.Name){exit 4}
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($doc.Current.Name))
"""
_ENCODED_SCRIPT = base64.b64encode(_PS_SCRIPT.encode("utf-16le")).decode("ascii")


def active_codex_title(timeout=4):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", _ENCODED_SCRIPT],
        capture_output=True, timeout=timeout, creationflags=flags, check=False,
    )
    if result.returncode:
        raise RuntimeError("未检测到已打开的 Codex 当前任务")
    encoded = result.stdout.decode("ascii", errors="ignore").strip().splitlines()
    if not encoded:
        raise RuntimeError("Codex 未返回当前任务标题")
    return base64.b64decode(encoded[-1]).decode("utf-8").strip()


def match_active_task(tasks, title, saved_id=""):
    matches = [task for task in tasks if task.get("title", "").strip() == title.strip()]
    if not matches:
        raise RuntimeError(f"未能把当前 Codex 标题映射到任务 ID：{title}")
    if saved_id:
        saved = next((task for task in matches if task.get("id") == saved_id), None)
        if saved:
            return {**saved, "ambiguous": len(matches) > 1}
    return {**matches[0], "ambiguous": len(matches) > 1}


def resolve_active_codex_task(saved_id=""):
    title = active_codex_title()
    return match_active_task(discover_codex_tasks(limit=200), title, saved_id)
