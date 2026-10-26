"""后台任务：核对 / 生成 的进度、日志与结果。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

CHECK_STEPS = [
    ("read", "读取文件"),
    ("sch", "解析原理图"),
    ("pcb", "解析 PCB"),
    ("baseline", "校验基准"),
    ("scan", "逐条核对 BOM"),
    ("report", "生成结果"),
]

GENERATE_STEPS = [
    ("read", "读取文件"),
    ("sch", "解析原理图"),
    ("pcb", "解析 PCB"),
    ("merge", "合并元件"),
    ("match", "匹配物料总表"),
    ("write", "写入 BOM"),
]


def _stamp() -> str:
    return time.strftime("%H:%M:%S")


class Task:
    def __init__(self, kind: str, title: str, store, steps: list[tuple[str, str]]):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self._store = store
        self.createdAt = time.strftime("%Y-%m-%d %H:%M:%S")
        self.started = time.time()
        self.finishedAt: str | None = None
        self.status = "running"
        self.error = ""
        self.progress = 0
        self.metrics: dict[str, Any] = {}
        self.files: dict[str, Any] = {}
        self.output: dict[str, Any] | None = None
        self.result: dict[str, Any] = {}
        self.steps = [{"key": k, "name": n, "state": "pending", "note": ""} for k, n in steps]
        self.logs: list[dict[str, str]] = []
        self._cancel = False
        self._lock = threading.Lock()

    # -- 进度 API（供 run 函数调用） --------------------------------------
    def emit(self, level: str, text: str) -> None:
        with self._lock:
            self.logs.append({"time": _stamp(), "level": level, "text": text})
            if len(self.logs) > 400:
                del self.logs[:100]

    def step(self, key: str, state: str, note: str = "") -> None:
        with self._lock:
            total = len(self.steps)
            for i, s in enumerate(self.steps):
                if s["key"] == key:
                    s["state"] = state
                    if note:
                        s["note"] = note
                    if state in ("done", "failed"):
                        self.progress = max(self.progress, int((i + 1) * 100 / total))
                    break
            else:
                return

    def active(self, key: str, note: str = "") -> None:
        self.step(key, "active", note)

    def set_progress(self, pct: int) -> None:
        with self._lock:
            self.progress = max(self.progress, min(99, int(pct)))

    @property
    def cancelled(self) -> bool:
        return self._cancel

    def cancel(self) -> None:
        self._cancel = True

    # -- 快照 -------------------------------------------------------------
    def public(self, with_result: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "createdAt": self.createdAt,
            "finishedAt": self.finishedAt,
            "progress": self.progress,
            "steps": self.steps,
            "logs": self.logs[-200:],
            "metrics": self.metrics,
            "files": self.files,
            "output": self.output,
            "error": self.error,
            "elapsed": round(time.time() - self.started, 2),
        }
        if with_result:
            data["result"] = self.result
        return data

    def persist(self) -> None:
        snapshot = self.public(with_result=True)
        snapshot["resultFull"] = self.result
        if len(self.logs) > 60:
            snapshot["logs"] = self.logs[:20] + self.logs[-40:]
        self._store.persist_task(snapshot)


def submit(store, kind: str, title: str, steps, run: Callable[[Task], None]) -> Task:
    task = Task(kind, title, store, steps)
    store.tasks[task.id] = task
    task.persist()
    store._save_state()

    def worker() -> None:
        try:
            run(task)
            if task.cancelled:
                task.status = "cancelled"
                task.emit("WARN", "任务已取消")
            else:
                task.status = "done"
        except Exception as exc:  # 让失败原因出现在界面上
            task.status = "failed"
            task.error = str(exc)
            task.emit("ERROR", f"任务失败：{exc}")
        finally:
            task.progress = 100 if task.status == "done" else task.progress
            task.finishedAt = time.strftime("%Y-%m-%d %H:%M:%S")
            for s in task.steps:
                if s["state"] in ("pending", "active") and task.status == "failed":
                    s["state"] = "pending"
            task.persist()
            store._save_state()

    threading.Thread(target=worker, name=f"task-{task.id}", daemon=True).start()
    return task


def public_of(obj, with_result: bool = False) -> dict[str, Any]:
    """把内存中的 Task 或磁盘上恢复的任务字典统一成前端可用的结构。"""
    if isinstance(obj, Task):
        return obj.public(with_result=with_result)
    data = dict(obj)
    data["result"] = data.pop("resultFull", data.get("result", {})) or {}
    return data


def find(store, task_id: str) -> dict[str, Any] | None:
    task = store.tasks.get(task_id)
    if task is None:
        return None
    return public_of(task, with_result=True)
