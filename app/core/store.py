"""运行期工作区：上传登记、物料总表、模板库、任务队列。"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from . import altium, bom_reader, master as master_mod, template as template_mod

STATE_FILE = "state.json"
TASKS_DIR = "tasks"

KINDS = ("schematic", "pcb", "bom", "master", "template")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class AppError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.uploads_dir = os.path.join(self.root, "uploads")
        self.outputs_dir = os.path.join(self.root, "outputs")
        self.tasks_dir = os.path.join(self.root, TASKS_DIR)
        for d in (self.uploads_dir, self.outputs_dir, self.tasks_dir):
            os.makedirs(d, exist_ok=True)

        self.uploads: dict[str, dict[str, Any]] = {}
        self.selection: dict[str, str | None] = {k: None for k in KINDS}
        self.master: master_mod.MaterialMaster | None = None
        self.master_info: dict[str, Any] | None = None
        self.templates: list[dict[str, Any]] = []
        self.default_template_id: str | None = None
        self.tasks: dict[str, dict[str, Any]] = {}
        self.last_check_id: str | None = None
        self.last_generate_id: str | None = None
        self._state_path = os.path.join(self.root, STATE_FILE)
        self._load_state()

    # ------------------------------------------------------------------ 状态
    def _load_state(self) -> None:
        try:
            with open(self._state_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return

        for item in data.get("uploads", []):
            path = item.get("path")
            if not path or not os.path.exists(path):
                continue
            record = {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "size": item.get("size", 0),
                "path": path,
                "uploadedAt": item.get("uploadedAt", ""),
                "status": item.get("status", "已解析"),
                "summary": item.get("summary", {}),
                "error": item.get("error", ""),
            }
            if record["id"] and record["kind"]:
                self.uploads[record["id"]] = record

        for kind in KINDS:
            uid = (data.get("selection") or {}).get(kind)
            if uid and uid in self.uploads:
                self.selection[kind] = uid

        for item in data.get("templates", []):
            if os.path.exists(item.get("path", "")):
                self.templates.append(item)
        self.default_template_id = data.get("defaultTemplateId")

        mpath = data.get("masterPath")
        if mpath and os.path.exists(mpath):
            try:
                self.master = master_mod.load_master(mpath)
                self.master_info = data.get("masterInfo")
            except Exception:
                self.master = None

        for tid in data.get("taskIds", [])[-60:]:
            task = self._read_task(tid)
            if task:
                self.tasks[tid] = task
        self.last_check_id = data.get("lastCheckId")
        self.last_generate_id = data.get("lastGenerateId")
        if self.last_check_id not in self.tasks:
            self.last_check_id = None
        if self.last_generate_id not in self.tasks:
            self.last_generate_id = None

    def _save_state(self) -> None:
        payload = {
            "uploads": [
                {**_public_upload(r), "path": r["path"]} for r in self.uploads.values()
            ],
            "selection": self.selection,
            "templates": self.templates,
            "defaultTemplateId": self.default_template_id,
            "masterPath": self.master.source if self.master else None,
            "masterInfo": getattr(self, "master_info", None),
            "taskIds": list(self.tasks.keys()),
            "lastCheckId": self.last_check_id,
            "lastGenerateId": self.last_generate_id,
        }
        try:
            with open(self._state_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _task_path(self, tid: str) -> str:
        return os.path.join(self.tasks_dir, f"{tid}.json")

    def _read_task(self, tid: str) -> dict[str, Any] | None:
        try:
            with open(self._task_path(tid), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def persist_task(self, task: dict[str, Any]) -> None:
        try:
            with open(self._task_path(task["id"]), "w", encoding="utf-8") as fh:
                json.dump(task, fh, ensure_ascii=False)
        except OSError:
            pass

    # ------------------------------------------------------------------ 上传
    def register_upload(self, kind: str, filename: str, data: bytes) -> dict[str, Any]:
        if kind not in KINDS:
            raise AppError(f"未知的上传类型：{kind}")

        uid = uuid.uuid4().hex[:12]
        safe = os.path.basename(filename or "unnamed")
        path = os.path.join(self.uploads_dir, f"{uid}_{safe}")
        with open(path, "wb") as fh:
            fh.write(data)

        record: dict[str, Any] = {
            "id": uid,
            "kind": kind,
            "name": safe,
            "size": len(data),
            "path": path,
            "uploadedAt": _now(),
            "status": "待解析",
            "summary": {},
            "error": "",
        }

        try:
            record["summary"] = self._parse(record)
            record["status"] = "已解析"
        except Exception as exc:  # 解析失败要让用户看到原因
            record["status"] = "解析失败"
            record["error"] = str(exc)

        self.uploads[uid] = record
        if record["status"] == "已解析":
            if kind == "master":
                self.master = master_mod.load_master(path)
                self.master_info = {"name": safe, "size": len(data), "syncedAt": _now(),
                                    **self.master.summary()}
                self._save_state()
            elif kind == "template":
                info = template_mod.inspect_template(path, display_name=safe)
                entry = {"id": uid, "name": safe, "path": path, "size": len(data),
                         "syncedAt": _now(), **info.summary()}
                entry["name"] = safe
                self.templates = [t for t in self.templates if t["id"] != uid] + [entry]
                if not self.default_template_id:
                    self.default_template_id = uid
            self.selection[kind] = uid
        self._save_state()
        return record

    def _parse(self, record: dict[str, Any]) -> dict[str, Any]:
        kind = record["kind"]
        path = record["path"]
        if kind == "schematic":
            data = open(path, "rb").read()
            info = altium.extract_sch(data, record["name"])
            return {
                "components": len(info["components"]),
                "records": info["record_count"],
                "format": "OLE 复合文档" if altium.is_ole(data) else "文本记录",
                "refs": len(info["designators"]),
                "streams": [s for s, _ in info["streams"][:6]] if info["streams"] else [],
            }
        if kind == "pcb":
            data = open(path, "rb").read()
            info = altium.extract_pcb(data, record["name"])
            return {
                "components": info["component_count"],
                "refs": len(info["designators"]),
                "unlabeled": len(info["unlabeled"]),
                "patterns": len({c["pattern"] for c in info["components"] if c["pattern"]}),
                "format": "OLE 复合文档" if altium.is_ole(data) else "文本记录",
            }
        if kind == "bom":
            info = bom_reader.load_bom(path)
            return info.summary()
        if kind == "master":
            m = master_mod.load_master(path)
            return m.summary()
        if kind == "template":
            t = template_mod.inspect_template(path)
            return t.summary()
        return {}

    def get_upload(self, uid: str | None, kind: str | None = None) -> dict[str, Any]:
        if not uid:
            raise AppError(f"缺少{_kind_label(kind)}文件，请先上传")
        record = self.uploads.get(uid)
        if not record:
            raise AppError(f"{_kind_label(kind)}文件已失效，请重新上传")
        if record["status"] != "已解析":
            raise AppError(f"{record['name']} 解析失败：{record['error']}")
        return record

    def ensure_baseline(self) -> dict[str, Any]:
        """核对/生成前确认必需输入就绪。"""
        missing = []
        for kind, label in (("schematic", "原理图"), ("pcb", "PCB")):
            uid = self.selection.get(kind)
            if not uid or uid not in self.uploads:
                missing.append(label)
        return {"missing": missing, "masterReady": self.master is not None}

    # ------------------------------------------------------------------ 模板
    def template_entry(self, tid: str | None) -> dict[str, Any] | None:
        if not tid:
            return None
        for t in self.templates:
            if t["id"] == tid:
                return t
        return None

    def current_template(self):
        entry = self.template_entry(self.default_template_id) or (
            self.templates[0] if self.templates else None
        )
        if not entry or not os.path.exists(entry["path"]):
            return template_mod.builtin_template()
        return template_mod.inspect_template(entry["path"], display_name=entry["name"])

    def material_summary(self) -> dict[str, Any] | None:
        if not self.master:
            return None
        info = dict(getattr(self, "master_info", None) or {})
        info.update(self.master.summary())
        return info

    def snapshot(self) -> dict[str, Any]:
        """给前端的整体状态快照。"""
        from . import jobs

        selection = {}
        for kind, uid in self.selection.items():
            rec = self.uploads.get(uid) if uid else None
            selection[kind] = _public_upload(rec) if rec else None

        def brief(tid: str | None) -> dict[str, Any] | None:
            if not tid or tid not in self.tasks:
                return None
            return _task_brief(jobs.public_of(self.tasks[tid]))

        views = sorted(
            (jobs.public_of(t) for t in self.tasks.values()),
            key=lambda t: t.get("createdAt", ""),
            reverse=True,
        )

        return {
            "selection": selection,
            "material": self.material_summary(),
            "templates": [
                {**_public_template(t), "isDefault": t["id"] == self.default_template_id}
                for t in self.templates
            ],
            "defaultTemplateId": self.default_template_id,
            "tasks": [_task_brief(t) for t in views[:20]],
            "lastCheck": brief(self.last_check_id),
            "lastGenerate": brief(self.last_generate_id),
            "baseline": self.ensure_baseline(),
        }


def _kind_label(kind: str | None) -> str:
    return {
        "schematic": "原理图",
        "pcb": "PCB",
        "bom": "待核对 BOM",
        "master": "物料总表",
        "template": "BOM 模板",
    }.get(kind or "", "输入")


def _public_upload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "kind": record["kind"],
        "name": record["name"],
        "size": record["size"],
        "status": record["status"],
        "error": record["error"],
        "uploadedAt": record["uploadedAt"],
        "summary": record["summary"],
    }


def _public_template(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": t["id"],
        "name": t["name"],
        "size": t["size"],
        "syncedAt": t["syncedAt"],
        "columnCount": t.get("columnCount"),
        "columns": t.get("columns", []),
        "fields": t.get("fields", {}),
        "headerRow": t.get("headerRow"),
        "sheet": t.get("sheet"),
        "freeze": t.get("freeze"),
        "filter": t.get("filter"),
        "builtin": t.get("builtin", False),
    }


def _task_brief(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "id": task["id"],
        "kind": task["kind"],
        "title": task.get("title", ""),
        "status": task["status"],
        "createdAt": task["createdAt"],
        "finishedAt": task.get("finishedAt"),
        "progress": task.get("progress", 0),
        "metrics": task.get("metrics", {}),
        "files": task.get("files", {}),
        "output": task.get("output"),
    }
