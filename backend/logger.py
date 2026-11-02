# -*- coding: utf-8 -*-
"""极简日志：写入 data/app.log，方便排查开机自启 / 通知问题。"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()
_log_file: Path | None = None


def configure(data_dir: Path) -> Path:
    global _log_file
    data_dir.mkdir(parents=True, exist_ok=True)
    _log_file = Path(data_dir) / "app.log"
    return _log_file


def log(message: str) -> None:
    if _log_file is None:
        return
    try:
        with _lock:
            if _log_file.exists() and _log_file.stat().st_size > 512 * 1024:
                _log_file.write_text("", encoding="utf-8")
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with _log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {message}\n")
    except OSError:
        pass
