# -*- coding: utf-8 -*-
"""月度总结统计：为图表页提供聚合数据 + 自动生成的文字结语。"""

from __future__ import annotations

from datetime import date, timedelta

from store import CATEGORIES, WEEKDAY_NAMES, add_months

PERIODS = [
    ("上午", 6, 12),
    ("下午", 12, 18),
    ("晚上", 18, 24),
    ("凌晨", 0, 6),
]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = add_months(first, 1) - timedelta(days=1)
    return first, last


def _hour_bucket(time_text: str) -> str:
    try:
        hour = int(str(time_text).split(":")[0])
    except (ValueError, IndexError, TypeError):
        hour = 9
    for name, start, end in PERIODS:
        if start <= hour < end:
            return name
    return "上午"


def monthly_stats(store, year: int, month: int) -> dict:
    first, last = month_bounds(year, month)
    occurrences = store.occurrences(first, last)

    total = len(occurrences)
    done = sum(1 for o in occurrences if o["done"])
    rate = round(done / total * 100) if total else 0

    daily = []
    cursor = first
    while cursor <= last:
        key = cursor.isoformat()
        items = [o for o in occurrences if o["date"] == key]
        daily.append({
            "day": cursor.day,
            "date": key,
            "weekday": WEEKDAY_NAMES[cursor.weekday()],
            "total": len(items),
            "done": sum(1 for o in items if o["done"]),
        })
        cursor += timedelta(days=1)

    categories = []
    for cat in CATEGORIES:
        items = [o for o in occurrences if o["category"] == cat["key"]]
        categories.append({
            "key": cat["key"],
            "name": cat["name"],
            "color": cat["color"],
            "total": len(items),
            "done": sum(1 for o in items if o["done"]),
        })
    categories = [c for c in categories if c["total"] > 0]
    categories.sort(key=lambda c: c["total"], reverse=True)

    weekday = [{"name": name, "total": 0, "done": 0} for name in WEEKDAY_NAMES]
    for occ in occurrences:
        index = date.fromisoformat(occ["date"]).weekday()
        weekday[index]["total"] += 1
        weekday[index]["done"] += 1 if occ["done"] else 0

    periods = {name: {"name": name, "total": 0, "done": 0} for name, _, _ in PERIODS}
    for occ in occurrences:
        bucket = periods[_hour_bucket(occ["time"])]
        bucket["total"] += 1
        bucket["done"] += 1 if occ["done"] else 0
    period_list = [periods[name] for name, _, _ in PERIODS]

    busiest_day = max(daily, key=lambda d: d["total"], default=None)
    if busiest_day and busiest_day["total"] == 0:
        busiest_day = None
    busiest_weekday = max(weekday, key=lambda w: w["total"], default=None)
    if busiest_weekday and busiest_weekday["total"] == 0:
        busiest_weekday = None
    top_category = categories[0] if categories else None
    active_days = sum(1 for d in daily if d["total"] > 0)
    repeat_count = sum(1 for o in occurrences if o["isRepeat"])
    finished_days = sum(1 for d in daily if d["total"] > 0 and d["done"] == d["total"])

    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    prev_first, prev_last = month_bounds(prev_year, prev_month)
    prev_total = len(store.occurrences(prev_first, prev_last))

    cumulative = []
    running_total = 0
    running_done = 0
    for item in daily:
        running_total += item["total"]
        running_done += item["done"]
        cumulative.append({
            "day": item["day"],
            "planned": running_total,
            "done": running_done,
        })

    month_label = f"{year}年{month}月"
    summary = _summary_text(
        month_label=month_label,
        total=total,
        done=done,
        rate=rate,
        active_days=active_days,
        days_in_month=(last - first).days + 1,
        busiest_day=busiest_day,
        top_category=top_category,
        periods=period_list,
        prev_total=prev_total,
        repeat_count=repeat_count,
    )

    return {
        "month": f"{year:04d}-{month:02d}",
        "monthLabel": month_label,
        "year": year,
        "monthNumber": month,
        "firstDate": first.isoformat(),
        "lastDate": last.isoformat(),
        "daysInMonth": (last - first).days + 1,
        "total": total,
        "done": done,
        "rate": rate,
        "activeDays": active_days,
        "finishedDays": finished_days,
        "repeatCount": repeat_count,
        "avgPerDay": round(total / ((last - first).days + 1), 1),
        "daily": daily,
        "cumulative": cumulative,
        "categories": categories,
        "weekday": weekday,
        "periods": period_list,
        "busiestDay": busiest_day,
        "busiestWeekday": busiest_weekday,
        "topCategory": top_category,
        "prevTotal": prev_total,
        "summary": summary,
    }


def _summary_text(month_label, total, done, rate, active_days, days_in_month,
                  busiest_day, top_category, periods, prev_total, repeat_count) -> str:
    if total == 0:
        return f"{month_label}还没有记录日程。添加第一条安排，月底就能在这里看到属于你的时间画像。"

    sentences = [f"{month_label}你一共安排了 {total} 项日程，完成 {done} 项，完成率 {rate}%。"]

    if rate >= 80:
        sentences.append("执行效率很稳，说到做到。")
    elif rate >= 50:
        sentences.append("节奏不错，还有一点收尾空间。")
    elif rate > 0:
        sentences.append("完成率偏低，可以试着把大任务拆小一些。")
    else:
        sentences.append("尚未标记完成，记得回来勾选一下。")

    sentences.append(
        f"有安排的日子 {active_days} 天，占整月的 {round(active_days / days_in_month * 100)}%。"
    )

    if busiest_day and busiest_day["total"] >= 2:
        sentences.append(
            f"{busiest_day['day']} 日最忙（{busiest_day['total']} 项），那天辛苦了。"
        )

    if top_category:
        sentences.append(
            f"{top_category['name']}类日程最多，共 {top_category['total']} 项。"
        )

    busy_period = max(periods or [], key=lambda p: p["total"], default=None)
    if busy_period and busy_period["total"] > 0:
        sentences.append(f"你更习惯把事安排在{busy_period['name']}。")

    if repeat_count:
        sentences.append(f"其中 {repeat_count} 项来自重复日程，规律让坚持更轻松。")

    if prev_total:
        diff = total - prev_total
        if diff > 0:
            sentences.append(f"比上月多安排了 {diff} 项，节奏更紧凑了。")
        elif diff < 0:
            sentences.append(f"比上月少 {abs(diff)} 项，给自己留出了更多空白。")
        else:
            sentences.append("与上月安排数量持平，节奏稳定。")

    return "".join(sentences)
