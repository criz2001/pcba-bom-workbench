"""本地 Web 服务：静态页面 + REST API。"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import BUILD, __version__  # noqa: E402
from app import flows  # noqa: E402
from app.core import altium, jobs, template as template_mod  # noqa: E402
from app.core.store import AppError, Store  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
PROJECT_DIR = os.path.dirname(BASE_DIR)


def resolve_workspace() -> str:
    """工作区（上传文件 / 输出结果 / 物料库）位置，优先级：

    1. 环境变量 BOM_WORKSPACE
    2. 项目目录下的 config.json（安装程序会写入，指向用户数据目录）
    3. 项目目录下的 workspace（开发态默认）
    """
    env = os.environ.get("BOM_WORKSPACE")
    if env:
        return os.path.abspath(env)

    config_path = os.path.join(PROJECT_DIR, "config.json")
    try:
        # utf-8-sig：安装脚本用 PowerShell 写的 JSON 可能带 BOM
        with open(config_path, encoding="utf-8-sig") as fh:
            path = (json.load(fh) or {}).get("workspace")
        if path:
            return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    except (OSError, ValueError):
        pass

    return os.path.join(PROJECT_DIR, "workspace")


WORKSPACE_DIR = resolve_workspace()

ALLOWED_EXT = {
    "schematic": {".schdoc", ".schdot"},
    "pcb": {".pcbdoc"},
    "bom": {".xlsx", ".xlsm", ".csv"},
    "master": {".xlsx", ".xlsm", ".csv"},
    "template": {".xlsx", ".xlsm"},
}
MAX_UPLOAD = 256 * 1024 * 1024


def create_app() -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="",
                template_folder=TEMPLATE_DIR)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
    app.json.ensure_ascii = False

    store = Store(WORKSPACE_DIR)
    app.extensions["store"] = store

    # ------------------------------------------------------------- 页面
    PAGES = {
        "/": ("workbench", "workbench"),
        "/check/setup": ("check_setup", "check-setup"),
        "/check/running": ("check_running", "check-running"),
        "/check/result": ("check_result", "check-result"),
        "/check/detail": ("check_detail", "check-detail"),
        "/gen/setup": ("gen_setup", "gen-setup"),
        "/gen/result": ("gen_result", "gen-result"),
        "/library": ("library", "library"),
    }

    from flask import render_template

    def render(template: str, page_key: str):
        return render_template(
            f"{template}.html",
            page_key=page_key,
            engine_version=__version__,
            engine_build=BUILD,
        )

    for route, (template, page_key) in PAGES.items():
        app.add_url_rule(route, endpoint=f"page_{page_key}",
                         view_func=(lambda t=template, k=page_key: render(t, k)))

    @app.get("/favicon.ico")
    def favicon():
        # 桌面窗口后端会主动请求 favicon，这里直接回 204，避免日志里出现 404
        return "", 204

    @app.get("/api/status")
    def status():
        return jsonify(
            {
                "ok": True,
                "engine": {"name": "核对 / 生成引擎", "version": __version__, "build": BUILD,
                           "ready": True, "mode": "本地模式"},
                "workspace": store.root,
            }
        )

    @app.get("/api/state")
    def state():
        data = store.snapshot()
        data["engine"] = {"version": __version__, "build": BUILD, "ready": True}
        return jsonify({"ok": True, **data})

    # ------------------------------------------------------------- 上传
    @app.post("/api/upload")
    def upload():
        kind = (request.form.get("kind") or "").strip()
        if kind not in ALLOWED_EXT:
            raise AppError(f"未知的上传类型：{kind or '(空)'}")
        if "file" not in request.files:
            raise AppError("未收到文件")
        file = request.files["file"]
        name = file.filename or ""
        if not name:
            raise AppError("文件名为空")
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_EXT[kind]:
            allowed = "、".join(sorted(ALLOWED_EXT[kind]))
            raise AppError(f"{_label(kind)} 仅支持 {allowed}，当前为 {ext or '(无扩展名)'}")

        data = file.read()
        if not data:
            raise AppError("文件内容为空")
        record = store.register_upload(kind, name, data)
        return jsonify({"ok": True, "upload": _public(record), "selection": store.selection})

    @app.post("/api/selection")
    def selection():
        body = _json()
        for kind in ("schematic", "pcb", "bom", "master", "template"):
            if kind in body:
                value = body[kind]
                if value and value not in store.uploads:
                    raise AppError(f"{_label(kind)}对应的上传已失效，请重新上传")
                store.selection[kind] = value
                if kind == "template":
                    store.default_template_id = value
        store._save_state()
        return jsonify({"ok": True, "selection": store.selection})

    @app.post("/api/upload/clear")
    def clear_uploads():
        body = _json()
        kinds = body.get("kinds") or list(ALLOWED_EXT)
        for kind in kinds:
            uid = store.selection.get(kind)
            if uid:
                record = store.uploads.pop(uid, None)
                if record and body.get("deleteFile") and os.path.exists(record["path"]):
                    try:
                        os.remove(record["path"])
                    except OSError:
                        pass
            store.selection[kind] = None
        if "master" in kinds:
            store.master = None
            store.master_info = None
        if "template" in kinds:
            store.templates = []
            store.default_template_id = None
        store._save_state()
        return jsonify({"ok": True, "selection": store.selection})

    # ------------------------------------------------------------- 基准校验
    @app.post("/api/baseline")
    def baseline():
        """比较 PCB 与原理图的位号集合，供「文件与规则」页实时提示版次是否对齐。"""
        body = _json()
        try:
            sch_rec = store.get_upload(body.get("schematicId") or store.selection.get("schematic"), "schematic")
            pcb_rec = store.get_upload(body.get("pcbId") or store.selection.get("pcb"), "pcb")
        except AppError as exc:
            return jsonify({"ok": True, "ready": False, "reason": str(exc)})

        sch = altium.extract_sch(open(sch_rec["path"], "rb").read(), sch_rec["name"])
        pcb = altium.extract_pcb(open(pcb_rec["path"], "rb").read(), pcb_rec["name"])
        sch_refs = {c["designator"].strip() for c in sch["components"] if c["designator"]}
        pcb_refs = {c["designator"].strip() for c in pcb["components"] if c["designator"]}

        return jsonify(
            {
                "ok": True,
                "ready": True,
                "identical": sch_refs == pcb_refs,
                "schCount": len(sch_refs),
                "pcbCount": len(pcb_refs),
                "schComponents": len(sch["components"]),
                "pcbComponents": pcb["component_count"],
                "onlySchematic": sorted(sch_refs - pcb_refs, key=altium.ref_sort_key),
                "onlyPcb": sorted(pcb_refs - sch_refs, key=altium.ref_sort_key),
                "unlabeledPcb": [
                    {"pattern": c.get("pattern", ""), "libref": c.get("libref", "")}
                    for c in pcb["unlabeled"]
                ],
                "masterReady": store.master is not None,
            }
        )

    # ------------------------------------------------------------- 核对
    @app.post("/api/check/run")
    def check_run():
        body = _json()
        baseline = store.ensure_baseline()
        if baseline["missing"]:
            raise AppError("缺少必需输入：" + "、".join(baseline["missing"]))
        bom_id = body.get("bomId") or store.selection.get("bom")
        if not bom_id:
            raise AppError("缺少必需输入：待核对 BOM")

        options = body.get("options") or {}
        task = jobs.submit(
            store, "check",
            "BOM 三方核对",
            jobs.CHECK_STEPS,
            lambda t: flows.run_check(store, t, body),
        )
        store.last_check_id = task.id
        store._save_state()
        return jsonify({"ok": True, "taskId": task.id})

    # ------------------------------------------------------------- 生成
    @app.post("/api/generate/preview")
    def generate_preview():
        body = _json()
        baseline = store.ensure_baseline()
        if baseline["missing"]:
            raise AppError("缺少必需输入：" + "、".join(baseline["missing"]))

        sch_rec = store.get_upload(body.get("schematicId") or store.selection.get("schematic"), "schematic")
        pcb_rec = store.get_upload(body.get("pcbId") or store.selection.get("pcb"), "pcb")
        sch = altium.extract_sch(open(sch_rec["path"], "rb").read(), sch_rec["name"])
        pcb = altium.extract_pcb(open(pcb_rec["path"], "rb").read(), pcb_rec["name"])

        from app.core import generator

        try:
            data = generator.preview(sch, pcb, store.master)
        except ValueError as exc:
            raise AppError(str(exc)) from exc

        data["template"] = store.current_template().summary()
        data["templateId"] = store.default_template_id
        return jsonify({"ok": True, **data})

    @app.post("/api/generate/run")
    def generate_run():
        body = _json()
        baseline = store.ensure_baseline()
        if baseline["missing"]:
            raise AppError("缺少必需输入：" + "、".join(baseline["missing"]))
        task = jobs.submit(
            store, "generate",
            "BOM 生成",
            jobs.GENERATE_STEPS,
            lambda t: flows.run_generate(store, t, body),
        )
        store.last_generate_id = task.id
        store._save_state()
        return jsonify({"ok": True, "taskId": task.id})

    # ------------------------------------------------------------- 任务
    @app.get("/api/tasks")
    def tasks():
        items = [jobs.find(store, tid) for tid in reversed(list(store.tasks.keys()))]
        return jsonify({"ok": True, "tasks": [t for t in items if t][:30]})

    @app.get("/api/tasks/<task_id>")
    def task_detail(task_id: str):
        data = jobs.find(store, task_id)
        if data is None:
            raise AppError("任务不存在或已清理", 404)
        return jsonify({"ok": True, "task": data})

    @app.get("/api/tasks/<task_id>/result")
    def task_result(task_id: str):
        data = jobs.find(store, task_id)
        if data is None:
            raise AppError("任务不存在或已清理", 404)
        if data["status"] != "done":
            raise AppError(f"任务尚未完成（当前状态：{data['status']}）")
        return jsonify({"ok": True, "task": data, "result": data.get("result") or {}})

    @app.post("/api/tasks/<task_id>/cancel")
    def task_cancel(task_id: str):
        task = store.tasks.get(task_id)
        if task is None:
            raise AppError("任务不存在或已清理", 404)
        if isinstance(task, jobs.Task):
            task.cancel()
        return jsonify({"ok": True})

    @app.get("/api/tasks/<task_id>/download")
    def task_download(task_id: str):
        data = jobs.find(store, task_id)
        if data is None or not data.get("output"):
            raise AppError("该任务没有可下载的结果文件", 404)
        path = data["output"]["path"]
        if not os.path.exists(path):
            raise AppError("结果文件已被移除", 404)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.delete("/api/tasks/<task_id>")
    def task_delete(task_id: str):
        task = store.tasks.pop(task_id, None)
        if task is None:
            raise AppError("任务不存在", 404)
        path = os.path.join(store.tasks_dir, f"{task_id}.json")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        if store.last_check_id == task_id:
            store.last_check_id = None
        if store.last_generate_id == task_id:
            store.last_generate_id = None
        store._save_state()
        return jsonify({"ok": True})

    # ------------------------------------------------------------- 物料库
    @app.get("/api/library/materials")
    def materials():
        if store.master is None:
            return jsonify({"ok": True, "loaded": False, "total": 0, "rows": [],
                            "summary": None})
        query = request.args.get("query", "")
        status = request.args.get("status", "all")
        page = max(1, _int(request.args.get("page"), 1))
        size = min(200, max(5, _int(request.args.get("pageSize"), 10)))
        rows = store.master.search(query, status)
        total = len(rows)
        start = (page - 1) * size
        return jsonify(
            {
                "ok": True,
                "loaded": True,
                "total": total,
                "page": page,
                "pageSize": size,
                "rows": rows[start:start + size],
                "summary": store.material_summary(),
            }
        )

    @app.post("/api/library/templates/<template_id>/default")
    def set_default_template(template_id: str):
        if store.template_entry(template_id) is None:
            raise AppError("模板不存在", 404)
        store.default_template_id = template_id
        store._save_state()
        return jsonify({"ok": True, "defaultTemplateId": template_id})

    @app.delete("/api/library/templates/<template_id>")
    def delete_template(template_id: str):
        entry = store.template_entry(template_id)
        if entry is None:
            raise AppError("模板不存在", 404)
        store.templates = [t for t in store.templates if t["id"] != template_id]
        if store.default_template_id == template_id:
            store.default_template_id = store.templates[0]["id"] if store.templates else None
        store.uploads.pop(template_id, None)
        if store.selection.get("template") == template_id:
            store.selection["template"] = store.default_template_id
        store._save_state()
        return jsonify({"ok": True})

    @app.get("/api/library/templates")
    def templates():
        return jsonify({"ok": True, "templates": store.snapshot()["templates"],
                        "defaultTemplateId": store.default_template_id})

    @app.get("/api/template/inspect")
    def template_inspect():
        path = request.args.get("path")
        if path:
            if not os.path.exists(path):
                raise AppError("模板文件不存在", 404)
            tmpl = template_mod.inspect_template(path)
        else:
            tmpl = store.current_template()
        return jsonify({"ok": True, "template": tmpl.summary()})

    # ------------------------------------------------------------- 异常
    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        return jsonify({"ok": False, "error": str(exc)}), exc.status

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        """404/405 等保持原状态码，不要被下面的兜底当成 500。"""
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": exc.description}), exc.code
        return exc

    @app.errorhandler(Exception)
    def handle_error(exc: Exception):  # pragma: no cover - 兜底
        if isinstance(exc, AppError):
            return handle_app_error(exc)
        if isinstance(exc, HTTPException):
            return handle_http_error(exc)
        import traceback

        traceback.print_exc()
        return jsonify({"ok": False, "error": f"服务端异常：{exc}"}), 500

    return app


def _json() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _label(kind: str) -> str:
    return {"schematic": "原理图", "pcb": "PCB", "bom": "BOM 表",
            "master": "物料总表", "template": "BOM 模板"}.get(kind, kind)


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"], "kind": record["kind"], "name": record["name"],
        "size": record["size"], "status": record["status"], "error": record["error"],
        "summary": record["summary"],
    }


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("BOM_PORT", "8760"))
    host = os.environ.get("BOM_HOST", "127.0.0.1")
    url = f"http://{host}:{port}/"
    print("=" * 62)
    print("  PCBA BOM 工作台（本地模式）")
    print(f"  地址：{url}")
    print(f"  工作区：{WORKSPACE_DIR}")
    print("  关闭本窗口即可退出")
    print("=" * 62)

    if os.environ.get("BOM_NO_BROWSER") != "1":
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False, threaded=True)
