"""训练窗口进度显示：进度条、已用时间、预计剩余时间；同时写日志和状态文件。"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from .config import HEADER, LOGS


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Monitor:
    def __init__(self, name: str, total_units: int):
        LOGS.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.total = max(1, int(total_units))
        self.done = 0
        self.t0 = time.time()
        self.stage = ""
        self.log_path = LOGS / f"{name}.log"
        self.status_path = LOGS / f"{name}.status.json"
        self._fh = open(self.log_path, "w", encoding="utf-8")
        self._last_draw = 0.0
        self.line("=" * 78)
        self.line(f"[{name}] {HEADER}")
        self.line(f"[{name}] 预计拟合单元 {self.total}，开始 {time.strftime('%H:%M:%S')}")
        self.line("=" * 78)
        self._status("running")

    # ---- 输出 ----
    def line(self, text: str):
        sys.stdout.write("\r" + " " * 110 + "\r" + text + "\n")
        sys.stdout.flush()
        self._fh.write(time.strftime("%H:%M:%S ") + text + "\n")
        self._fh.flush()
        self._draw(force=True)

    def set_stage(self, text: str):
        self.stage = text
        self._draw(force=True)

    def tick(self, n: int = 1, note: str = ""):
        self.done += n
        if self.done > self.total:
            self.total = self.done
        if note:
            self.stage = note
        self._draw()

    def _draw(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_draw < 0.3:
            return
        self._last_draw = now
        frac = min(1.0, self.done / self.total)
        el = now - self.t0
        eta = el / frac - el if frac > 0 else 0
        bar = "#" * int(30 * frac) + "." * (30 - int(30 * frac))
        stage = self.stage[:44]
        sys.stdout.write(f"\r[{bar}] {frac*100:5.1f}% {self.done}/{self.total} 用时 {_fmt(el)} 剩余 {_fmt(eta)} | {stage:<44}")
        sys.stdout.flush()
        if force or int(now) % 5 == 0:
            self._status("running")

    def _status(self, state: str, extra: dict | None = None):
        rec = {"name": self.name, "state": state, "done": self.done, "total": self.total,
               "elapsed_s": round(time.time() - self.t0, 1), "stage": self.stage,
               "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        if extra:
            rec.update(extra)
        self.status_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    def finish(self, extra: dict | None = None):
        self.done = self.total
        self._draw(force=True)
        self.line(f"[{self.name}] 完成，用时 {_fmt(time.time() - self.t0)}")
        self._status("done", extra)
        self._fh.close()

    def fail(self, exc: BaseException):
        self.line(f"[{self.name}] 失败：{exc!r}")
        self.line(traceback.format_exc())
        self._status("failed", {"error": repr(exc)})
        self._fh.close()


def run_main(name: str, total_units: int, fn):
    """统一入口：异常时写 failed 状态，窗口保持打开由 PowerShell -NoExit 负责。"""
    mon = Monitor(name, total_units)
    try:
        extra = fn(mon)
        mon.finish(extra)
        return 0
    except BaseException as exc:  # noqa: BLE001
        mon.fail(exc)
        return 1
