# -*- coding: utf-8 -*-
"""Windows 系统集成：Toast 通知、快捷方式、开机自启。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from logger import log

BASE = Path(__file__).resolve().parent.parent
BACKEND = BASE / "backend"
ICON = BASE / "assets" / "icon.ico"

TOAST_SCRIPT = BACKEND / "toast.ps1"
SHORTCUT_SCRIPT = BACKEND / "shortcuts.ps1"
REGISTER_SCRIPT = BACKEND / "register-aumid.ps1"
POPUP_SCRIPT = BACKEND / "popup.py"

APP_ID = "MySchedule.Desktop"
# 未注册自定义 AppUserModelID 时，退回到 Windows 自带的 PowerShell AUMID（通知仍可弹出）
FALLBACK_APP_ID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"

APP_NAME = "我的日程"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

# 由 app.py 在服务启动后设置，用于提醒小窗里的"打开日程"
APP_URL = "http://127.0.0.1:47823/"


def configure(app_url: str) -> None:
    global APP_URL
    APP_URL = app_url


# ---------------------------------------------------------------- PowerShell
def _powershell() -> str:
    for name in ("powershell.exe", "pwsh.exe"):
        found = _which(name)
        if found:
            return found
    return "powershell.exe"


def _which(name: str) -> str | None:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(folder) / name
        if candidate.exists():
            return str(candidate)
    return None


def _run_ps(script: Path, args: list[str], timeout: int = 40) -> tuple[bool, str]:
    if not script.exists():
        return False, f"missing script: {script}"
    command = [
        _powershell(), "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", str(script), *args,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"powershell 执行失败: {exc}")
        return False, str(exc)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    ok = result.returncode == 0
    if not ok:
        log(f"powershell 返回 {result.returncode}: {output[:400]}")
    return ok, output


# ---------------------------------------------------------------- 系统通知
def _pythonw() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def _send_windows_toast(payload: dict) -> bool:
    handle, path = tempfile.mkstemp(prefix="myschedule-toast-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)
        ok, output = _run_ps(TOAST_SCRIPT, ["-Path", path])
        if not ok:
            log(f"系统通知发送失败: {output[:300]}")
        return ok
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _send_popup(title: str, body: str) -> bool:
    """系统通知不可用时，弹出桌面提醒小窗。"""
    if not POPUP_SCRIPT.exists():
        return False
    payload = {"title": title, "body": body, "url": APP_URL}
    handle, path = tempfile.mkstemp(prefix="myschedule-popup-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)
        subprocess.Popen(
            [_pythonw(), str(POPUP_SCRIPT), path],
            close_fds=True,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        )
        log("已弹出桌面提醒窗")
        return True
    except OSError as exc:
        log(f"桌面提醒窗启动失败: {exc}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False


def show_toast(title: str, body: str, app_id: str | None = None) -> bool:
    """弹出提醒：优先系统通知，失败则桌面小窗，保证用户能看到。"""
    payload = {
        "title": title,
        "body": body,
        "appId": app_id or registered_app_id(),
        "actionLabel": "打开日程",
    }
    ok = _send_windows_toast(payload)
    if not ok:
        _send_popup(title, body)
    return ok


# ---------------------------------------------------------------- 快捷方式
def start_menu_programs() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def startup_folder() -> Path:
    return start_menu_programs() / "Startup"


def desktop_folder() -> Path:
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    onedrive = home / "OneDrive" / "Desktop"
    desktop = home / "Desktop"
    if onedrive.is_dir() and not desktop.is_dir():
        return onedrive
    return desktop


def launch_command() -> tuple[str, str]:
    """返回 (可执行文件, 参数)，用于快捷方式启动本应用。"""
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
    app_py = BACKEND / "app.py"
    return str(executable), f'"{app_py}"'


def create_shortcut(lnk_path: Path, target: str, arguments: str,
                    app_id: str = "", description: str = APP_NAME) -> tuple[bool, str]:
    ok, output = _run_ps(SHORTCUT_SCRIPT, [
        "-LnkPath", str(lnk_path),
        "-TargetPath", target,
        "-Arguments", arguments,
        "-WorkingDirectory", str(BASE),
        "-IconLocation", str(ICON),
        "-Description", description,
        *(["-AppId", app_id] if app_id else []),
    ])
    # 脚本返回 0 不代表文件真的落地（权限 / 重定向都可能造成假成功），这里再确认一次
    if ok and not Path(lnk_path).exists():
        log(f"快捷方式未被创建: {lnk_path} | 输出: {output[:200]}")
        return False, f"快捷方式未生成（可能无权限）：{lnk_path}"
    return ok, output


def remove_shortcut(lnk_path: Path) -> tuple[bool, str]:
    return _run_ps(SHORTCUT_SCRIPT, ["-LnkPath", str(lnk_path), "-Remove"])


_registered: str | None = None


def ensure_registered(data_dir: Path) -> str:
    """首次运行注册本应用的通知身份，返回通知使用的 AppID。

    两种方式互为备份：
      1) 注册表 HKCU\\SOFTWARE\\Classes\\AppUserModelId
      2) 开始菜单快捷方式 + AppUserModelID 属性
    """
    global _registered
    if _registered:
        return _registered

    marker = Path(data_dir) / "notify-appid.txt"
    menu_lnk = start_menu_programs() / f"{APP_NAME}.lnk"
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        # 标记文件存在、但注册痕迹已经没了（重装 / 手动清理过）时，重新注册一次
        if value and menu_lnk.exists():
            _registered = value
            return _registered
        log("通知身份标记已失效（缺少开始菜单快捷方式），重新注册")

    registered = False

    ok, output = _run_ps(REGISTER_SCRIPT, [
        "-AppId", APP_ID,
        "-DisplayName", APP_NAME,
        "-IconPath", str(ICON.with_name("icon.png")),
    ])
    if ok:
        registered = True
        log("已通过注册表注册通知身份")
    else:
        log(f"注册表注册通知身份失败: {output[:200]}")

    target, arguments = launch_command()
    lnk = start_menu_programs() / f"{APP_NAME}.lnk"
    ok, output = create_shortcut(lnk, target, arguments, app_id=APP_ID,
                                 description=f"{APP_NAME} · 日程与提醒")
    if ok and "ok-with-appid" in output:
        registered = True
        log("已创建开始菜单快捷方式并写入 AppUserModelID")
    elif not lnk.exists():
        log(f"开始菜单快捷方式创建失败: {output[:200]}")

    _registered = APP_ID if registered else FALLBACK_APP_ID
    if not registered:
        log("通知身份注册未完成，提醒将使用桌面小窗")
    try:
        marker.write_text(_registered, encoding="utf-8")
    except OSError:
        pass
    return _registered


def registered_app_id() -> str:
    return _registered or FALLBACK_APP_ID


# ---------------------------------------------------------------- 开机自启
AUTOSTART_LNK_NAME = "我的日程.lnk"


def autostart_enabled() -> bool:
    return (startup_folder() / AUTOSTART_LNK_NAME).exists()


def set_autostart(enabled: bool) -> tuple[bool, str]:
    lnk = startup_folder() / AUTOSTART_LNK_NAME
    if enabled:
        target, arguments = launch_command()
        ok, output = create_shortcut(lnk, target, f"{arguments} --boot", description=f"{APP_NAME} · 开机提醒")
        log(f"开启开机自启: ok={ok} {output[:200]}")
        return ok, output
    ok, output = remove_shortcut(lnk)
    log(f"关闭开机自启: ok={ok} {output[:200]}")
    return ok, output


def create_desktop_shortcut() -> tuple[bool, str]:
    target, arguments = launch_command()
    lnk = desktop_folder() / f"{APP_NAME}.lnk"
    ok, output = create_shortcut(lnk, target, arguments, description=f"{APP_NAME} · 日程与提醒")
    return ok, str(lnk)


def open_path(path: Path) -> None:
    try:
        os.startfile(str(path))
    except OSError as exc:
        log(f"打开路径失败: {exc}")


def notify_available() -> bool:
    return _powershell() is not None and TOAST_SCRIPT.exists()
