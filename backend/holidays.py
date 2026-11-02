# -*- coding: utf-8 -*-
"""中国法定节假日与调休数据。

数据来源：国务院办公厅历年《关于部分节假日安排的通知》，存放在 holidays.json。
- type = "rest"：放假（含节假日与周末调休连休）
- type = "work"：调休上班日（原本周末，因放假而上班）
- festival = true：该节日真正的日期（用于当天提醒）

对于数据未覆盖的年份，用固定日期与清明算法兜底，保证元旦/清明/劳动节/国庆不会漏提醒。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

# 固定日期的法定节日（每年同一天）
FIXED_FESTIVALS = [
    ((1, 1), "元旦"),
    ((5, 1), "劳动节"),
    ((10, 1), "国庆节"),
]

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def qingming_day(year: int) -> int:
    """清明节气所在日（2000-2099 通用公式，与官方日期一致）。"""
    y = year - 2000
    return int(y * 0.2422 + 4.81) - int(y / 4)


def _parse(text) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


class HolidayStore:
    def __init__(self, builtin_path: Path, override_path: Path | None = None):
        self.source = ""
        self.updated = ""
        self.provisional_years: list[int] = []
        self._days: dict[str, dict] = {}

        builtin = self._read(builtin_path)
        if builtin:
            self._merge(builtin)

        # 用户可在数据目录放同名文件覆盖或补充（新增年份时无需重新打包）
        if override_path and Path(override_path).exists():
            extra = self._read(Path(override_path))
            if extra:
                self._merge(extra, override=True)

    # ---------------------------------------------------------------- 读取
    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    def _merge(self, payload: dict, override: bool = False) -> None:
        if not override:
            self.source = str(payload.get("source") or self.source)
            self.updated = str(payload.get("updated") or self.updated)
            for year in payload.get("provisionalYears") or []:
                try:
                    self.provisional_years.append(int(year))
                except (TypeError, ValueError):
                    continue
        for key, value in (payload.get("days") or {}).items():
            day = _parse(key)
            if not day or not isinstance(value, dict):
                continue
            kind = str(value.get("type") or "").strip()
            if kind not in ("rest", "work"):
                continue
            self._days[day.isoformat()] = {
                "type": kind,
                "name": str(value.get("name") or "节假日"),
                "festival": bool(value.get("festival")),
            }

    # ---------------------------------------------------------------- 查询
    def info(self, day: date) -> dict | None:
        """返回某天的节假日信息；数据未覆盖时按固定节日兜底。"""
        key = day.isoformat()
        data = self._days.get(key)
        if data:
            return dict(data)
        return self._fallback(day)

    @staticmethod
    def _fallback(day: date) -> dict | None:
        for (month, day_of_month), name in FIXED_FESTIVALS:
            if day.month == month and day.day == day_of_month:
                return {"type": "rest", "name": name, "festival": True, "synthetic": True}
        if day.month == 4 and day.day == qingming_day(day.year):
            return {"type": "rest", "name": "清明节", "festival": True, "synthetic": True}
        return None

    def has_data(self, year: int) -> bool:
        return any(key.startswith(str(year)) for key in self._days)

    def month_map(self, year: int, month: int) -> dict[str, dict]:
        result: dict[str, dict] = {}
        cursor = date(year, month, 1)
        while cursor.month == month:
            data = self.info(cursor)
            if data:
                result[cursor.isoformat()] = data
            cursor += timedelta(days=1)
        return result

    def block(self, day: date) -> dict | None:
        """计算某天所在的连续放假区间。"""
        data = self.info(day)
        if not data or data["type"] != "rest":
            return None
        start = day
        while True:
            previous = start - timedelta(days=1)
            info = self.info(previous)
            if not info or info["type"] != "rest":
                break
            start = previous
        end = day
        while True:
            following = end + timedelta(days=1)
            info = self.info(following)
            if not info or info["type"] != "rest":
                break
            end = following
        total = (end - start).days + 1
        index = (day - start).days + 1

        name = data["name"]
        if not data.get("festival"):
            cursor = start
            while cursor <= end:
                info = self.info(cursor)
                if info and info.get("festival"):
                    name = info["name"]
                    break
                cursor += timedelta(days=1)

        return {
            "name": name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": total,
            "index": index,
            "isFirst": index == 1,
            "isLast": index == total,
            "hasData": self.has_data(start.year),
            "provisional": start.year in self.provisional_years,
        }

    def status(self, day: date) -> dict | None:
        """当天用于提醒的文案信息。"""
        data = self.info(day)
        if not data:
            return None
        if data["type"] == "work":
            weekday = WEEKDAY_NAMES[day.weekday()]
            return {
                "type": "work",
                "name": data["name"],
                "title": f"今天是调休上班日（{weekday}）",
                "detail": data["name"],
            }
        block = self.block(day)
        if not block:
            return None
        if block["days"] <= 1:
            title = f"今天是{data['name']}"
            detail = "祝你度过愉快的一天"
        elif block["isFirst"]:
            title = f"今天是{block['name']}，假期开始"
            detail = f"共 {block['days']} 天假期"
        elif data.get("festival"):
            title = f"今天是{data['name']}"
            detail = f"假期第 {block['index']} 天，共 {block['days']} 天"
        else:
            title = f"{block['name']}假期第 {block['index']} 天"
            detail = f"共 {block['days']} 天，还剩 {block['days'] - block['index']} 天"
        return {
            "type": "rest",
            "name": data["name"],
            "title": title,
            "detail": detail,
            "block": block,
        }

    def upcoming(self, today: date, limit: int = 3) -> list[dict]:
        """从今天起之后的放假区间（含今天所在的区间）。"""
        result: list[dict] = []
        seen: set[str] = set()
        cursor = today
        for _ in range(400):
            info = self.info(cursor)
            if info and info["type"] == "rest":
                block = self.block(cursor)
                if block and block["start"] not in seen:
                    seen.add(block["start"])
                    result.append(block)
                    if len(result) >= limit:
                        break
                cursor = _parse(block["end"]) + timedelta(days=1)
                continue
            cursor += timedelta(days=1)
        return result

    def coverage(self) -> dict:
        years = sorted({int(key[:4]) for key in self._days})
        return {
            "source": self.source,
            "updated": self.updated,
            "years": years,
            "provisionalYears": sorted(set(self.provisional_years)),
        }
