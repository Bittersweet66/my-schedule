# -*- coding: utf-8 -*-
"""我的日程 · 本地服务

- 提供本地 Web 界面（web/）
- 提供 JSON API（/api/*）
- 后台调度：日程提醒、每日待办推送、开机播报、月度总结、节假日提醒
- 自动以 Edge/Chrome 的"应用模式"打开独立窗口

运行方式：pythonw backend/app.py [--boot]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen

import logger
import notify
from holidays import HolidayStore
from stats import monthly_stats
from store import CATEGORIES, REPEAT_NAMES, Store

BASE = Path(__file__).resolve().parent.parent
WEB_DIR = BASE / "web"
ASSET_DIR = BASE / "assets"
VERSION = "1.1.0"
APP_SIGNATURE = "my-schedule"
APP_WINDOW_TITLE = "我的日程"
DEFAULT_PORT = 47823
PORT_CANDIDATES = list(range(47823, 47845))

CREATE_NO_WINDOW = 0x08000000

# 应用窗口专用的浏览器配置目录（由 main() 设置）：让窗口不受日常 Edge 状态影响
BROWSER_PROFILE: Path | None = None


def configure_browser_profile(path: Path) -> None:
    global BROWSER_PROFILE
    BROWSER_PROFILE = Path(path)


log = logger.log


# ====================================================================== 应用状态
class AppState:
    def __init__(self, store: Store, boot_mode: bool):
        self.store = store
        self.boot_mode = boot_mode
        self.boot_digest: dict | None = None
        self.notifications: list[dict] = []
        self._notify_id = 0
        self._lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None
        self.stopping = threading.Event()
        self.started_at = datetime.now()
        # 节假日数据：内置数据 + 数据目录下的同名文件（便于用户自行更新年份）
        self.holidays = HolidayStore(
            BASE / "backend" / "holidays.json",
            Path(store.dir) / "holidays.json",
        )

    # ------------------------------------------------------------- 应用内消息
    def push_notification(self, kind: str, title: str, body: str,
                          items: list[dict] | None = None) -> dict:
        with self._lock:
            self._notify_id += 1
            payload = {
                "id": self._notify_id,
                "kind": kind,
                "title": title,
                "body": body,
                "items": items or [],
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            self.notifications.append(payload)
            self.notifications = self.notifications[-60:]
            return payload

    def notifications_since(self, since: int) -> list[dict]:
        with self._lock:
            return [n for n in self.notifications if n["id"] > since]


# ====================================================================== 文案
def today_occurrences(app: AppState) -> list[dict]:
    return app.store.occurrences_on(date.today())


def digest_payload(app: AppState) -> dict:
    items = today_occurrences(app)
    pending = [item for item in items if not item["done"]]
    holiday = app.holidays.status(date.today())

    if not items:
        title = "今天暂无安排"
        body = "给自己留一点空白吧。"
    else:
        title = f"今天有 {len(items)} 项待办"
        if len(pending) != len(items):
            title += f"（还剩 {len(pending)} 项）"
        lines = [f"{item['time']} {item['title']}" for item in items[:5]]
        if len(items) > 5:
            lines.append(f"……等共 {len(items)} 项")
        body = "\n".join(lines)

    if holiday:
        if holiday["type"] == "rest":
            title = holiday["title"]
            lines = [holiday.get("detail") or ""]
            if items:
                lines.append(f"今天另有 {len(items)} 项安排：")
                lines.extend(f"{item['time']} {item['title']}" for item in items[:4])
            body = "\n".join([line for line in lines if line])
        else:
            body = holiday["title"] + "\n" + body

    return {
        "date": date.today().isoformat(),
        "title": title,
        "body": body,
        "total": len(items),
        "pending": len(pending),
        "items": items[:8],
        "holiday": holiday,
    }


def reminder_text(occ: dict) -> str:
    parts = [f"{occ['time']} 开始"]
    if occ.get("categoryName"):
        parts.append(occ["categoryName"])
    if occ.get("note"):
        parts.append(occ["note"][:40])
    return " · ".join(parts)


def send_boot_digest(app: AppState) -> None:
    payload = digest_payload(app)
    app.boot_digest = payload
    log(f"开机播报: {payload['title']} / {payload['total']} 项")
    notify.show_toast(payload["title"], payload["body"])
    app.push_notification("digest", payload["title"], payload["body"], payload["items"])


def send_digest(app: AppState) -> None:
    payload = digest_payload(app)
    if not payload["total"] and not payload.get("holiday"):
        return
    notify.show_toast(payload["title"], payload["body"])
    app.push_notification("digest", payload["title"], payload["body"], payload["items"])
    log(f"每日推送: {payload['title']}")


def send_month_summary(app: AppState) -> None:
    today = date.today()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    stats = monthly_stats(app.store, year, month)
    if not stats["total"]:
        log("上月没有日程记录，跳过月度总结推送")
        return
    title = f"{stats['monthLabel']}总结"
    body = f"完成 {stats['done']}/{stats['total']} 项，完成率 {stats['rate']}%。"
    notify.show_toast(title, body)
    app.push_notification("summary", title, body)
    log(f"月度总结推送: {title}")


# ====================================================================== 调度器
def scheduler_loop(app: AppState) -> None:
    last_cleanup = None
    while not app.stopping.wait(20):
        try:
            tick(app)
            stamp = date.today()
            if last_cleanup != stamp:
                app.store.cleanup_notified()
                last_cleanup = stamp
                sync_autostart_state(app)
        except Exception as exc:  # 调度器不能挂
            log(f"调度异常: {exc}\n{traceback.format_exc()}")


def tick(app: AppState) -> None:
    now = datetime.now()
    settings = app.store.settings

    # 1) 日程到点提醒
    reminder_enabled = settings.get("defaultRemindBefore", 10) is not None
    due = app.store.pending_reminders(now)
    if due and reminder_enabled:
        for occ in due:
            title = occ["title"]
            body = reminder_text(occ)
            if occ["remindBefore"] == 0:
                body = "现在开始 · " + body
            else:
                body = f"还有 {occ['remindBefore']} 分钟 · " + body
            notify.show_toast(title, body)
            app.push_notification("reminder", title, body, [occ])
            log(f"提醒: {occ['occurrenceId']} {title}")
        app.store.mark_notified([occ["occurrenceId"] for occ in due])

    # 2) 每日待办推送
    digest_time = settings.get("digestTime", "08:30")
    now_hm = now.strftime("%H:%M")
    today_key = now.date().isoformat()
    if (settings.get("digestEnabled") and now_hm >= digest_time
            and settings.get("lastDigestDate") != today_key):
        app.store.patch_settings({"lastDigestDate": today_key})
        send_digest(app)

    # 3) 每月初推送上月总结
    month_key = f"{now.year:04d}-{now.month:02d}"
    settings = app.store.settings  # 重新读取，避免用到旧的 lastDigestDate
    if (settings.get("monthlySummaryNotify") and now.day <= 3 and now_hm >= digest_time
            and settings.get("lastSummaryMonth") != month_key):
        app.store.patch_settings({"lastSummaryMonth": month_key})
        send_month_summary(app)

    # 4) 节假日当天提醒（每日待办已推送到当天时，不再重复弹窗）
    holiday = app.holidays.status(now.date())
    if (settings.get("holidayNotify", True) and holiday
            and settings.get("lastHolidayDate") != today_key):
        already_sent = settings.get("lastDigestDate") == today_key and now_hm >= digest_time
        app.store.patch_settings({"lastHolidayDate": today_key})
        if not already_sent:
            notify.show_toast(holiday["title"], holiday.get("detail") or "")
            app.push_notification("holiday", holiday["title"], holiday.get("detail") or "")
            log(f"节假日提醒: {holiday['title']}")


def sync_autostart_state(app: AppState) -> None:
    actual = notify.autostart_enabled()
    if bool(app.store.settings.get("autostart")) != actual:
        app.store.patch_settings({"autostart": actual})


# ====================================================================== 窗口
def chromium_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Public"))
    pf = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    pf86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
    return [
        pf86 / "Microsoft/Edge/Application/msedge.exe",
        pf / "Microsoft/Edge/Application/msedge.exe",
        local / "Microsoft/Edge/Application/msedge.exe",
        pf / "Google/Chrome/Application/chrome.exe",
        pf86 / "Google/Chrome/Application/chrome.exe",
        local / "Google/Chrome/Application/chrome.exe",
    ]


def open_window(port: int) -> bool:
    """打开应用窗口，并**确认窗口真的出现了**。

    浏览器进程启动成功 ≠ 窗口出现：Edge/Chrome 在已有实例时会"交棒"给现有进程，
    Popen 不报错但窗口可能因为浏览器状态异常而不出现。所以这里统一用窗口枚举来验证：

    1. 已有「我的日程」窗口 → 直接切到前台（双击 = 唤起）
    2. Edge / Chrome 应用模式
    3. 系统默认浏览器（普通标签页，最不可能失败）

    每一步都校验窗口是否真的出现，没出现就换下一种方式。
    """
    url = f"http://127.0.0.1:{port}/"

    if _focus_app_window():
        log("已把应用窗口切到前台")
        return True

    # 记录启动前的窗口句柄快照，之后只关心"新出现的窗口"
    baseline = {hwnd for hwnd, _title, _cls in _top_level_windows()}

    exes = [exe for exe in chromium_candidates() if exe.exists()]
    # 优先用 Chrome：实测普通窗口模式下它最可靠
    exes.sort(key=lambda exe: 0 if exe.name.lower().startswith("chrome") else 1)

    # 1) 经 cmd 的 start 打开（和双击批处理完全一样，实测最可靠）
    for exe in exes[:2]:
        if not _cmd_start(exe, url):
            continue
        ok, detail = _wait_for_window(baseline, 12.0)
        if ok:
            log(f"已用 start 打开 {exe.name}（{detail}）: {url}")
            return True
        log(f"start {exe.name} 未能打开界面，看到的窗口: {detail}")

    # 2) 直接启动浏览器进程（不走 cmd）
    for exe in exes[:2]:
        if not _launch([str(exe), url]):
            continue
        ok, detail = _wait_for_window(baseline, 8.0)
        if ok:
            log(f"已用 {exe.name} 打开界面（{detail}）: {url}")
            return True
        log(f"{exe.name} 未能打开界面，看到的窗口: {detail}")

    # 兜底：交给系统外壳（默认浏览器关联损坏时会静默失败）
    if _shell_open(url):
        ok, detail = _wait_for_window(baseline, 10.0)
        if ok:
            log(f"已通过系统外壳打开（{detail}）: {url}")
            return True
        log(f"系统外壳未产生窗口，看到的窗口: {detail}")

    log("所有打开窗口的方式都未生效")
    return False


def _launch(cmd: list[str]) -> bool:
    """直接启动浏览器进程（窗口是否出现由 _wait_for_window 判定）。"""
    try:
        subprocess.Popen(cmd, startupinfo=_startup_info())
    except OSError as exc:
        log(f"窗口启动失败({Path(cmd[0]).name}): {exc}")
        return False
    time.sleep(0.6)
    return True


def _cmd_start(exe: Path, url: str) -> bool:
    """用 cmd 的 start 打开浏览器（与"双击一个批处理"完全相同的路径）。

    实测：直接 CreateProcess 启动 Chrome/Edge 时，进程会立刻退出、窗口不出现；
    而经 `start` 启动则正常 —— 所以优先走这条路径。
    """
    command = f'start "" "{exe}" "{url}"'
    try:
        subprocess.Popen(command, shell=True, startupinfo=_startup_info())
    except OSError as exc:
        log(f"start 启动失败({exe.name}): {exc}")
        return False
    time.sleep(0.8)
    return True


def _startup_info() -> subprocess.STARTUPINFO:
    """显式要求子进程以正常窗口显示（避免继承隐藏状态导致窗口不可见）。"""
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 1  # SW_SHOWNORMAL
    return info


def _shell_open(url: str) -> bool:
    """通过系统外壳打开 URL（走 explorer.exe，不受本进程启动状态影响）。"""
    try:
        import ctypes
        result = ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1)
        return int(result) > 32
    except Exception as exc:
        log(f"ShellExecute 打开失败: {exc}")
        return False


def _top_level_windows() -> list[tuple[int, str, str]]:
    """枚举当前可见的顶层窗口 (hwnd, 标题, 窗口类名)。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    result: list[tuple[int, str, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _param):
        try:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                class_buffer = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buffer, 256)
                result.append((hwnd, buffer.value, class_buffer.value))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return result


def _is_browser_window(class_name: str) -> bool:
    """Chromium 系浏览器的窗口类名，用来把记事本等无关窗口排除掉。"""
    return class_name.startswith("Chrome_WidgetWin")


def _find_app_window() -> int:
    try:
        for hwnd, title, _cls in _top_level_windows():
            if APP_WINDOW_TITLE in title:
                return hwnd
    except Exception as exc:
        log(f"枚举窗口失败: {exc}")
    return 0


def _focus_app_window() -> bool:
    hwnd = _find_app_window()
    if not hwnd:
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception as exc:
        log(f"窗口前置失败: {exc}")
        return False


def _wait_for_window(baseline: set[int], timeout: float) -> tuple[bool, str]:
    """等待出现新的**浏览器**窗口（记事本、资源管理器之类的窗口一律忽略）。

    页面加载完成后标题会变成「我的日程」；即使还没加载完，只要 Chromium 窗口出现
    也认为界面已经打开（此时再开第二个只会更乱）。
    """
    deadline = time.time() + timeout
    last = "(无新窗口)"
    while True:
        current = _top_level_windows()
        # 普通窗口可能是给已有浏览器开一个新标签页（窗口句柄不变），
        # 所以这里检查所有窗口的标题，而不只是新窗口
        if any(APP_WINDOW_TITLE in title for _hwnd, title, _cls in current):
            return True, "页面已加载"
        new = [item for item in current if item[0] not in baseline]
        browsers = [item for item in new if _is_browser_window(item[2])]
        if new:
            last = " / ".join(f"{title or '(无标题)'}[{cls}]" for _h, title, cls in new)[:200]
        if browsers:
            return True, "浏览器窗口已打开"
        if time.time() >= deadline:
            return False, last
        time.sleep(0.4)


# ====================================================================== HTTP
def month_range(month: str | None) -> tuple[date, date]:
    if month and re.fullmatch(r"\d{4}-\d{2}", month):
        year, mon = int(month[:4]), int(month[5:7])
    else:
        today = date.today()
        year, mon = today.year, today.month
    first = date(year, mon, 1)
    nxt = date(year + (mon == 12), (mon % 12) + 1, 1)
    return first, nxt - timedelta(days=1)


class Handler(BaseHTTPRequestHandler):
    server_version = f"MySchedule/{VERSION}"
    protocol_version = "HTTP/1.1"
    app: AppState  # 由 create_server 注入

    # ------------------------------------------------------------- 基础工具
    def log_message(self, fmt, *args):  # noqa: A003
        return

    def _send(self, status: int, body: bytes, content_type: str,
              extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1_000_000))
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------- 路由
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self._api(method, path, query)
            else:
                self._static(path)
        except Exception as exc:  # 兜底，避免服务线程被异常打挂
            log(f"请求异常 {method} {path}: {exc}\n{traceback.format_exc()}")
            try:
                self._error(f"服务器内部错误: {exc}", 500)
            except Exception:
                pass

    # ------------------------------------------------------------- 静态文件
    def _static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"

        if path.startswith("/assets/"):
            target = (ASSET_DIR / path[len("/assets/"):]).resolve()
            root = ASSET_DIR.resolve()
        else:
            target = (WEB_DIR / path.lstrip("/")).resolve()
            root = WEB_DIR.resolve()

        if not str(target).startswith(str(root)) or not target.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        suffix = target.suffix.lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".webmanifest": "application/manifest+json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(suffix) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"

        try:
            payload = target.read_bytes()
        except OSError:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        cache = "no-store" if suffix in (".html", ".js", ".css") else "public, max-age=86400"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ------------------------------------------------------------- API
    def _api(self, method: str, path: str, query: dict) -> None:
        app = self.app
        store = app.store

        if path == "/api/ping":
            self._json({"app": APP_SIGNATURE, "version": VERSION,
                        "pid": os.getpid(), "boot": app.boot_mode})
            return

        if path == "/api/bootstrap" and method == "GET":
            first, last = month_range((query.get("month") or [None])[0])
            settings = store.settings
            autostart = notify.autostart_enabled()
            if bool(settings.get("autostart")) != autostart:
                settings = store.patch_settings({"autostart": autostart})
            today = date.today()
            self._json({
                "app": {
                    "name": "我的日程",
                    "version": VERSION,
                    "bootMode": app.boot_mode,
                    "notifyAvailable": notify.notify_available(),
                    "dataDir": str(store.dir),
                    "startedAt": app.started_at.isoformat(timespec="seconds"),
                },
                "now": datetime.now().isoformat(timespec="seconds"),
                "today": date.today().isoformat(),
                "settings": settings,
                "categories": CATEGORIES,
                "repeatNames": REPEAT_NAMES,
                "month": first.strftime("%Y-%m"),
                "events": store.occurrences(first, last),
                "todayEvents": store.occurrences_on(date.today()),
                "bootDigest": app.boot_digest if app.boot_mode else None,
                "notifications": app.notifications_since(0)[-10:],
                "holidays": app.holidays.month_map(first.year, first.month),
                "holidayToday": app.holidays.status(today),
                "holidayUpcoming": app.holidays.upcoming(today, 3),
                "holidayMeta": app.holidays.coverage(),
            })
            return

        if path == "/api/holidays" and method == "GET":
            year_text = (query.get("year") or [str(date.today().year)])[0]
            try:
                year = int(year_text)
            except ValueError:
                year = date.today().year
            days = {}
            for month in range(1, 13):
                days.update(app.holidays.month_map(year, month))
            self._json({
                "year": year,
                "hasData": app.holidays.has_data(year),
                "days": days,
                "meta": app.holidays.coverage(),
            })
            return

        if path == "/api/events" and method == "POST":
            data = self._read_json()
            try:
                event = store.add_event(data)
            except ValueError as exc:
                self._error(str(exc))
                return
            self._json({"event": event})
            return

        match = re.fullmatch(r"/api/events/([\w\-@.]+)", path)
        if match and method == "PUT":
            event = store.update_event(match.group(1), self._read_json())
            if not event:
                self._error("日程不存在", 404)
                return
            self._json({"event": event})
            return

        if match and method == "DELETE":
            ok = store.delete_event(match.group(1))
            self._json({"deleted": ok})
            return

        match = re.fullmatch(r"/api/occurrences/([\w\-@.]+)/toggle", path)
        if match and method == "POST":
            occurrence_id = match.group(1)
            event_id, _, day = occurrence_id.partition("@")
            data = self._read_json()
            done = data.get("done")
            result = store.toggle_occurrence(event_id, day or data.get("date", ""),
                                             None if done is None else bool(done))
            if not result:
                self._error("日程不存在", 404)
                return
            self._json({"result": result})
            return

        if path == "/api/stats" and method == "GET":
            month = (query.get("month") or [""])[0]
            first, _ = month_range(month or None)
            self._json(monthly_stats(store, first.year, first.month))
            return

        if path == "/api/settings" and method == "PATCH":
            patch = self._read_json()
            if "autostart" in patch:
                notify.set_autostart(bool(patch["autostart"]))
            settings = store.patch_settings(patch)
            settings["autostart"] = notify.autostart_enabled()
            self._json({"settings": settings})
            return

        if path == "/api/notifications" and method == "GET":
            since = (query.get("since") or ["0"])[0]
            try:
                since_id = int(since)
            except ValueError:
                since_id = 0
            self._json({"items": app.notifications_since(since_id),
                        "digest": app.boot_digest if app.boot_mode else None})
            return

        if path == "/api/digest" and method == "POST":
            send_boot_digest(app)
            self._json({"digest": app.boot_digest})
            return

        if path == "/api/test-notify" and method == "POST":
            ok = notify.show_toast("测试通知", "如果你看到这条通知，提醒功能工作正常。")
            app.push_notification("test", "测试通知", "系统通知已发送")
            self._json({"ok": ok})
            return

        if path == "/api/desktop-shortcut" and method == "POST":
            ok, detail = notify.create_desktop_shortcut()
            self._json({"ok": ok, "detail": detail})
            return

        if path == "/api/open-data-dir" and method == "POST":
            notify.open_path(store.dir)
            self._json({"ok": True, "dir": str(store.dir)})
            return

        if path == "/api/shutdown" and method == "POST":
            self._json({"ok": True})
            threading.Timer(0.4, _shutdown, args=(app,)).start()
            return

        self._error("接口不存在", 404)


def _shutdown(app: AppState) -> None:
    app.stopping.set()
    if app.server:
        try:
            app.server.shutdown()
        except Exception:
            pass


def create_server(app: AppState, port: int) -> ThreadingHTTPServer:
    handler_class = type("BoundHandler", (Handler,), {"app": app})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        # Windows 上 SO_REUSEADDR 会让两个进程同时绑定同一端口（与 Linux 语义不同），
        # 这里关闭它，保证"端口已被占用"能被正确检测到，从而实现单实例。
        allow_reuse_address = False

    return Server(("127.0.0.1", port), handler_class)


# ====================================================================== 单实例
def is_our_app(port: int, timeout: float = 0.45) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("app") == APP_SIGNATURE
    except Exception:
        return False


# ====================================================================== 入口
def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="我的日程 本地服务")
    parser.add_argument("--boot", action="store_true", help="开机模式：播报今日待办")
    parser.add_argument("--no-window", action="store_true", help="不自动打开窗口")
    parser.add_argument("--data-dir", default="", help="数据目录（默认 data/）")
    parser.add_argument("--port", type=int, default=0, help="指定端口")
    parser.add_argument("--multi", action="store_true", help="允许同时运行多个实例（调试用）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data_dir = Path(args.data_dir).resolve() if args.data_dir else BASE / "data"
    logger.configure(data_dir)
    configure_browser_profile(data_dir / "browser-profile")
    log(f"===== 启动 我的日程 v{VERSION} =====")
    log(f"data_dir={data_dir} boot={args.boot} argv={sys.argv}")

    store = Store(data_dir)
    app = AppState(store, boot_mode=args.boot)

    # 直接尝试绑定端口：成功即本进程独占，失败再判断是否为已运行的实例。
    # （比逐个端口发请求探测快得多，避免启动耗时）
    server = None
    port = 0
    candidates = [args.port] if args.port else PORT_CANDIDATES
    for candidate in candidates:
        try:
            server = create_server(app, candidate)
            port = candidate
            break
        except OSError:
            if not args.multi and is_our_app(candidate):
                log(f"检测到已运行的实例（端口 {candidate}），把窗口叫到前台")
                if not args.no_window:
                    open_window(candidate)
                return 0
            if args.port:
                log(f"端口 {candidate} 已被占用")
                break
            continue

    if server is None:
        log("找不到可用端口，启动失败")
        return 1
    app.server = server

    server_thread = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    server_thread.start()
    notify.configure(f"http://127.0.0.1:{port}/")
    log(f"服务已启动: http://127.0.0.1:{port}/")

    threading.Thread(target=scheduler_loop, args=(app,), name="scheduler", daemon=True).start()

    def prepare_backend() -> None:
        try:
            notify.ensure_registered(data_dir)
            sync_autostart_state(app)
        except Exception as exc:
            log(f"初始化失败: {exc}")

    threading.Thread(target=prepare_backend, name="prepare", daemon=True).start()

    if args.boot:
        delay = 1.5 if store.settings.get("bootOpenWindow", True) else 0.5
        if store.settings.get("bootNotify", True):
            threading.Timer(delay + 2.0, send_boot_digest, args=(app,)).start()

    if not args.no_window:
        should_open = (not args.boot) or store.settings.get("bootOpenWindow", True)
        if should_open:
            threading.Timer(0.6, open_window, args=(port,)).start()

    try:
        while not app.stopping.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        app.stopping.set()
        try:
            server.shutdown()
        except Exception:
            pass
        log("===== 已退出 =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
