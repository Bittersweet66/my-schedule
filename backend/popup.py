# -*- coding: utf-8 -*-
"""桌面提醒小窗（系统 Toast 不可用时的兜底通道）。

由 app.py / notify.py 以独立进程方式拉起：
    pythonw backend/popup.py <payload.json>

payload: {"title": "...", "body": "...", "url": "http://127.0.0.1:47823/"}
"""

from __future__ import annotations

import json
import random
import sys
import webbrowser

WIDTH = 360
AUTO_CLOSE_MS = 15000


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return 1
    finally:
        try:
            import os
            os.remove(sys.argv[1])
        except OSError:
            pass

    title = str(data.get("title") or "我的日程")
    body = str(data.get("body") or "")
    url = str(data.get("url") or "")

    try:
        import tkinter as tk
        import tkinter.font as tkfont
    except ImportError:
        return 1

    try:
        root = tk.Tk()
    except Exception:
        return 1

    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.0)
    except Exception:
        pass
    root.configure(bg="#e9edf3")

    font_title = tkfont.Font(family="Microsoft YaHei", size=10, weight="bold")
    font_body = tkfont.Font(family="Microsoft YaHei", size=9)

    card = tk.Frame(root, bg="#ffffff", bd=0)
    card.pack(fill="both", expand=True, padx=1, pady=1)

    accent = tk.Frame(card, bg="#4567f2", width=4)
    accent.pack(side="left", fill="y")

    content = tk.Frame(card, bg="#ffffff", padx=14, pady=12)
    content.pack(side="left", fill="both", expand=True)

    head = tk.Frame(content, bg="#ffffff")
    head.pack(fill="x")
    tk.Label(head, text="🔔 我的日程", bg="#ffffff", fg="#98a3b7",
             font=tkfont.Font(family="Microsoft YaHei", size=8)).pack(side="left")

    close_btn = tk.Label(head, text="×", bg="#ffffff", fg="#b3bbc9",
                         font=tkfont.Font(family="Microsoft YaHei", size=12), cursor="hand2")
    close_btn.pack(side="right")

    tk.Label(content, text=title, bg="#ffffff", fg="#172033", font=font_title,
             wraplength=WIDTH - 70, justify="left", anchor="w").pack(fill="x", pady=(6, 4))

    if body:
        tk.Label(content, text=body, bg="#ffffff", fg="#718096", font=font_body,
                 wraplength=WIDTH - 70, justify="left", anchor="w").pack(fill="x")

    hint = tk.Label(content, text="点击打开日程 ›", bg="#ffffff", fg="#4567f2",
                    font=tkfont.Font(family="Microsoft YaHei", size=8), cursor="hand2")
    hint.pack(anchor="w", pady=(8, 0))

    root.update_idletasks()
    width = max(root.winfo_reqwidth(), WIDTH)
    height = root.winfo_reqheight()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = screen_w - width - 26
    y = screen_h - height - 90 - random.randint(0, 70)

    root.geometry(f"{width}x{height}+{x}+{y}")

    def fade_in(alpha: float = 0.0) -> None:
        if alpha < 0.98:
            alpha = min(0.98, alpha + 0.12)
            try:
                root.attributes("-alpha", alpha)
            except Exception:
                pass
            root.after(16, fade_in, alpha)

    def close(_event=None) -> None:
        try:
            root.destroy()
        except Exception:
            pass

    def open_app(_event=None) -> None:
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        close()

    for widget in (root, card, content, hint):
        widget.bind("<Button-1>", open_app)
    close_btn.bind("<Button-1>", close)
    root.bind("<Escape>", close)

    root.after(16, fade_in)
    root.after(AUTO_CLOSE_MS, close)
    try:
        root.mainloop()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
