# -*- coding: utf-8 -*-
"""日程数据层。

- 数据保存在 data/schedule.json（原子写入，避免写坏）
- 支持 每天 / 每周 / 每月 重复日程（按日期展开成"日程实例"）
- 完成状态：单次日程记在事件上，重复日程按日期记在 doneDates 上
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

CATEGORIES = [
    {"key": "work", "name": "工作", "color": "#4567f2"},
    {"key": "study", "name": "学习", "color": "#8b5cf6"},
    {"key": "life", "name": "生活", "color": "#e9914b"},
    {"key": "health", "name": "健康", "color": "#22b07d"},
    {"key": "other", "name": "其他", "color": "#7c8aa0"},
]
CATEGORY_MAP = {c["key"]: c for c in CATEGORIES}

REPEAT_KEYS = ["none", "daily", "weekly", "monthly"]
REPEAT_NAMES = {"none": "不重复", "daily": "每天", "weekly": "每周", "monthly": "每月"}

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

DEFAULT_SETTINGS = {
    "autostart": False,
    "bootNotify": True,
    "bootOpenWindow": True,
    "digestEnabled": True,
    "digestTime": "08:30",
    "defaultRemindBefore": 10,
    "monthlySummaryNotify": True,
    "holidayNotify": True,
    "lastDigestDate": "",
    "lastSummaryMonth": "",
    "lastHolidayDate": "",
    "notified": {},
}


def today_str() -> str:
    return date.today().isoformat()


def fmt_date(d: date) -> str:
    return d.isoformat()


def parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def add_months(d: date, months: int) -> date:
    """按月加，遇到月末自动取当月最后一天。"""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = d.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


def clamp_text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def norm_time(value, default: str = "09:00") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        hour, minute = text.split(":")[:2]
        h, m = int(hour), int(minute)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except (ValueError, TypeError):
        pass
    return default


def norm_date(value, default: str = "") -> str:
    text = str(value or "").strip()[:10]
    try:
        return parse_date(text).isoformat()
    except ValueError:
        return default or today_str()


def norm_remind(value) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return 10
    allowed = [-1, 0, 5, 10, 15, 30, 60, 120, 1440]
    return minutes if minutes in allowed else 10


def norm_repeat(value) -> str:
    text = str(value or "none").strip().lower()
    return text if text in REPEAT_KEYS else "none"


def norm_category(value) -> str:
    text = str(value or "").strip().lower()
    return text if text in CATEGORY_MAP else "other"


class Store:
    """线程安全的 JSON 数据仓库。"""

    def __init__(self, data_dir: Path | str):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "schedule.json"
        self._lock = threading.RLock()
        self._data = self._load()

    # ---------------------------------------------------------------- 读写
    def _load(self) -> dict:
        if self.file.exists():
            try:
                raw = json.loads(self.file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                raw = {}
        else:
            raw = {}
        data = {"version": 1, "events": [], "settings": {}}
        if isinstance(raw, dict):
            data["events"] = [e for e in raw.get("events", []) if isinstance(e, dict)]
            data["settings"] = raw.get("settings") or {}
        settings = dict(DEFAULT_SETTINGS)
        settings.update({k: v for k, v in data["settings"].items() if k in DEFAULT_SETTINGS})
        data["settings"] = settings
        return data

    def _save(self) -> None:
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.file)  # 原子替换

    # ---------------------------------------------------------------- 设置
    @property
    def settings(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data["settings"], ensure_ascii=False))

    def patch_settings(self, patch: dict) -> dict:
        with self._lock:
            for key, value in (patch or {}).items():
                if key not in DEFAULT_SETTINGS:
                    continue
                if key in ("bootNotify", "bootOpenWindow", "digestEnabled",
                           "autostart", "monthlySummaryNotify", "holidayNotify"):
                    self._data["settings"][key] = bool(value)
                elif key == "digestTime":
                    self._data["settings"][key] = norm_time(value, "08:30")
                elif key == "defaultRemindBefore":
                    self._data["settings"][key] = norm_remind(value)
                else:
                    self._data["settings"][key] = value
            self._save()
            return self.settings

    def mark_notified(self, keys: list[str]) -> None:
        """记录已提醒的日程实例，避免重复提醒。"""
        with self._lock:
            notified = self._data["settings"].setdefault("notified", {})
            stamp = datetime.now().isoformat(timespec="seconds")
            for key in keys:
                notified[key] = stamp
            if len(notified) > 2000:
                for key in sorted(notified, key=lambda k: notified[k])[: len(notified) - 2000]:
                    notified.pop(key, None)
            self._save()

    # ---------------------------------------------------------------- 事件
    def list_events(self) -> list[dict]:
        with self._lock:
            return json.loads(json.dumps(self._data["events"], ensure_ascii=False))

    def get_event(self, event_id: str) -> dict | None:
        with self._lock:
            for event in self._data["events"]:
                if event["id"] == event_id:
                    return json.loads(json.dumps(event, ensure_ascii=False))
        return None

    def _clean(self, payload: dict, base: dict | None = None) -> dict:
        src = dict(base or {})
        src.update({k: v for k, v in (payload or {}).items() if v is not None})

        title = clamp_text(src.get("title"), 60)
        if not title:
            raise ValueError("日程名称不能为空")

        remind = src.get("remindBefore", DEFAULT_SETTINGS["defaultRemindBefore"])
        return {
            "title": title,
            "date": norm_date(src.get("date")),
            "time": norm_time(src.get("time")),
            "endTime": norm_time(src.get("endTime"), "") if src.get("endTime") else "",
            "category": norm_category(src.get("category")),
            "note": clamp_text(src.get("note"), 300),
            "remindBefore": norm_remind(remind),
            "repeat": norm_repeat(src.get("repeat")),
        }

    def add_event(self, payload: dict) -> dict:
        clean = self._clean(payload)
        event = {
            "id": "ev_" + uuid.uuid4().hex[:10],
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "done": False,
            "doneDates": [],
        }
        event.update(clean)
        with self._lock:
            self._data["events"].append(event)
            self._save()
        return event

    def update_event(self, event_id: str, payload: dict) -> dict | None:
        with self._lock:
            for index, event in enumerate(self._data["events"]):
                if event["id"] != event_id:
                    continue
                merged = dict(event)
                merged.update(self._clean(payload, event))
                if payload.get("date") or payload.get("repeat"):
                    merged["doneDates"] = []
                    merged["done"] = False
                self._data["events"][index] = merged
                self._save()
                return merged
        return None

    def delete_event(self, event_id: str) -> bool:
        with self._lock:
            before = len(self._data["events"])
            self._data["events"] = [e for e in self._data["events"] if e["id"] != event_id]
            changed = len(self._data["events"]) != before
            if changed:
                self._save()
            return changed

    def toggle_occurrence(self, event_id: str, day: str, done: bool | None = None) -> dict | None:
        """切换某个日程实例的完成状态。"""
        with self._lock:
            for event in self._data["events"]:
                if event["id"] != event_id:
                    continue
                if event.get("repeat", "none") == "none":
                    event["done"] = (not event.get("done")) if done is None else bool(done)
                    result = {"id": event_id, "done": event["done"], "date": event["date"]}
                else:
                    dates = list(event.get("doneDates") or [])
                    is_done = day in dates
                    target = (not is_done) if done is None else bool(done)
                    if target and day not in dates:
                        dates.append(day)
                    if not target and day in dates:
                        dates.remove(day)
                    event["doneDates"] = sorted(dates)
                    result = {"id": event_id, "done": target, "date": day}
                self._save()
                return result
        return None

    # ---------------------------------------------------------------- 展开
    def _is_done(self, event: dict, day: str) -> bool:
        if event.get("repeat", "none") == "none":
            return bool(event.get("done"))
        return day in (event.get("doneDates") or [])

    def _iter_dates(self, event: dict, start: date, end: date):
        repeat = event.get("repeat", "none")
        try:
            origin = parse_date(event["date"])
        except (KeyError, ValueError):
            return
        if repeat == "none":
            if start <= origin <= end:
                yield origin
            return
        if repeat == "daily":
            cursor = max(origin, start)
            while cursor <= end:
                yield cursor
                cursor += timedelta(days=1)
            return
        if repeat == "weekly":
            cursor = max(origin, start)
            cursor += timedelta(days=(origin.weekday() - cursor.weekday()) % 7)
            while cursor <= end:
                if cursor >= origin:
                    yield cursor
                cursor += timedelta(days=7)
            return
        if repeat == "monthly":
            month_index = 0
            while True:
                cursor = add_months(origin, month_index)
                if cursor > end:
                    break
                if cursor >= start and cursor >= origin:
                    yield cursor
                month_index += 1

    def occurrences(self, start: date, end: date) -> list[dict]:
        """返回 [start, end] 区间内的日程实例（已按日期/时间排序）。"""
        result: list[dict] = []
        for event in self.list_events():
            for day in self._iter_dates(event, start, end):
                day_str = fmt_date(day)
                category = CATEGORY_MAP.get(event.get("category"), CATEGORY_MAP["other"])
                result.append({
                    "id": event["id"],
                    "occurrenceId": f"{event['id']}@{day_str}",
                    "eventId": event["id"],
                    "title": event.get("title", ""),
                    "date": day_str,
                    "time": event.get("time", "09:00"),
                    "endTime": event.get("endTime", ""),
                    "category": category["key"],
                    "categoryName": category["name"],
                    "color": category["color"],
                    "note": event.get("note", ""),
                    "remindBefore": event.get("remindBefore", 10),
                    "repeat": event.get("repeat", "none"),
                    "repeatName": REPEAT_NAMES.get(event.get("repeat", "none"), "不重复"),
                    "isRepeat": event.get("repeat", "none") != "none",
                    "done": self._is_done(event, day_str),
                })
        result.sort(key=lambda item: (item["date"], item["time"], item["title"]))
        return result

    def occurrences_on(self, day: date) -> list[dict]:
        return self.occurrences(day, day)

    def pending_reminders(self, now: datetime, window_minutes: int = 120) -> list[dict]:
        """到点需要提醒的日程实例。"""
        items = []
        notified = self.settings.get("notified") or {}
        for occ in self.occurrences_on(now.date()):
            if occ["done"] or occ["remindBefore"] < 0:
                continue
            if occ["occurrenceId"] in notified:
                continue
            try:
                hour, minute = occ["time"].split(":")
                due = datetime.combine(now.date(), datetime.min.time()).replace(
                    hour=int(hour), minute=int(minute))
                due -= timedelta(minutes=int(occ["remindBefore"]))
            except (ValueError, TypeError):
                continue
            delta = (now - due).total_seconds() / 60
            if -1 <= delta <= window_minutes:
                items.append({**occ, "dueAt": due.isoformat(timespec="minutes"), "lateMinutes": int(max(delta, 0))})
        return items

    def cleanup_notified(self) -> None:
        """清理 3 天前的提醒记录。"""
        with self._lock:
            notified = self._data["settings"].get("notified") or {}
            limit = date.today() - timedelta(days=3)
            keep = {}
            for key, stamp in notified.items():
                day = key.split("@")[-1][:10]
                try:
                    if parse_date(day) >= limit:
                        keep[key] = stamp
                except ValueError:
                    keep[key] = stamp
            self._data["settings"]["notified"] = keep
            self._save()
