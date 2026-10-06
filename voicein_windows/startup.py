import base64
import subprocess
import sys
import winreg
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "VoiceIn"


def executable_command():
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve()), "--background"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = Path(__file__).with_name("launcher.pyw").resolve()
    return str(pythonw), f'"{launcher}" --background'


def launch_command():
    executable, arguments = executable_command()
    escaped = executable.replace("'", "''")
    args = arguments.replace("'", "''")
    command = f"Start-Sleep -Seconds 20; Start-Process -FilePath '{escaped}'"
    if args:
        command += f" -ArgumentList '{args}'"
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    return f'powershell.exe -NoProfile -WindowStyle Hidden -EncodedCommand {encoded}'


def set_autostart(enabled=True):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def create_manual_shortcuts():
    executable, arguments = executable_command()
    exe = executable.replace("'", "''")
    args = arguments.replace("'", "''")
    ps = f"""
$exePath = '{exe}'
$exeArgs = '{args}'
$ws = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VoiceIn.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'VoiceIn.lnk')
)
foreach ($linkPath in $targets) {{
    $shortcut = $ws.CreateShortcut($linkPath)
    $shortcut.TargetPath = $exePath
    $shortcut.Arguments = $exeArgs
    $shortcut.WorkingDirectory = Split-Path -Parent $exePath
    $shortcut.IconLocation = $exePath + ',0'
    $shortcut.Description = 'Start VoiceIn Windows speech input'
    $shortcut.Save()
}}
"""
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
        creationflags=subprocess.CREATE_NO_WINDOW,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode:
        raise OSError(result.stderr.strip() or f"PowerShell exit {result.returncode}")


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)[0] == launch_command()
    except FileNotFoundError:
        return False
