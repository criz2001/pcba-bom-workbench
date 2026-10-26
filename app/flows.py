"""核对与生成的完整流程（供后台任务调用）。"""

from __future__ import annotations

import os
import time
from typing import Any

from .core import altium, bom_reader, checker, generator, jobs, report
from .core import template as template_mod


def _safe_name(name: str) -> str:
    base = os.path.splitext(os.path.basename(name or "output"))[0]
    return "".join(c for c in base if c not in '\\/:*?"<>|').strip() or "output"


def run_check(store, task: jobs.Task, payload: dict[str, Any]) -> None:
    sel = store.selection
    options = payload.get("options") or {}

    # ---------- 1. 读取文件 ----------
    task.active("read", "读取 4 类输入")
    sch_rec = store.get_upload(payload.get("schematicId") or sel.get("schematic"), "schematic")
    pcb_rec = store.get_upload(payload.get("pcbId") or sel.get("pcb"), "pcb")
    bom_rec = store.get_upload(payload.get("bomId") or sel.get("bom"), "bom")
    master_rec = None
    master_id = payload.get("masterId") or sel.get("master")
    if master_id and master_id in store.uploads:
        master_rec = store.uploads[master_id]
        if master_rec["status"] != "已解析":
            master_rec = None

    task.files = {
        "schematic": {"id": sch_rec["id"], "name": sch_rec["name"], "size": sch_rec["size"]},
        "pcb": {"id": pcb_rec["id"], "name": pcb_rec["name"], "size": pcb_rec["size"]},
        "bom": {"id": bom_rec["id"], "name": bom_rec["name"], "size": bom_rec["size"]},
        "master": {"id": master_rec["id"], "name": master_rec["name"], "size": master_rec["size"]} if master_rec else None,
    }
    task.title = payload.get("title") or f"{_safe_name(bom_rec['name'])} 三方核对"
    task.emit("INFO", f"载入 {sch_rec['name']}（{_size(sch_rec['size'])}）")
    task.emit("INFO", f"载入 {pcb_rec['name']}（{_size(pcb_rec['size'])}）")
    task.emit("INFO", f"载入 {bom_rec['name']}（{_size(bom_rec['size'])}）")
    task.emit("INFO", f"物料总表：{master_rec['name']}" if master_rec
              else "物料总表未上传：跳过「编码不存在」与「名称与总表不符」两类核对")
    task.step("read", "done", "4 类输入已加载" if master_rec else "3 类输入已加载")

    if task.cancelled:
        return

    # ---------- 2. 解析原理图 ----------
    task.active("sch")
    sch = altium.extract_sch(open(sch_rec["path"], "rb").read(), sch_rec["name"])
    task.emit("INFO", f"原理图记录 {sch['record_count']} 条，提取元件 {len(sch['components'])} 个"
                      f"（OWNERINDEX +1 偏移已应用）")
    task.step("sch", "done", f"记录 {sch['record_count']} 条 · 元件 {len(sch['components'])}")
    task.set_progress(20)

    # ---------- 3. 解析 PCB ----------
    task.active("pcb")
    pcb = altium.extract_pcb(open(pcb_rec["path"], "rb").read(), pcb_rec["name"])
    task.emit("INFO", f"PCB Components6/Data 元件 {pcb['component_count']} 个，"
                      f"其中 {len(pcb['unlabeled'])} 个无 SOURCEDESIGNATOR")
    task.emit("INFO", "Pads6/Data 为纯二进制记录，跳过；改用原理图引脚数替代")
    task.step("pcb", "done", f"元件 {pcb['component_count']}")
    task.set_progress(35)

    # ---------- 4. 校验基准 ----------
    task.active("baseline")
    pcb_refs = {c["designator"].strip() for c in pcb["components"] if c["designator"]}
    sch_refs = {c["designator"].strip() for c in sch["components"] if c["designator"]}
    if pcb_refs == sch_refs:
        task.emit("OK", f"基准一致性校验通过：PCB 与原理图各 {len(pcb_refs)} 个位号，集合完全一致")
    else:
        task.emit("WARN", f"基准不一致：仅 PCB 有 {sorted(pcb_refs - sch_refs) or '无'}；"
                          f"仅原理图有 {sorted(sch_refs - pcb_refs) or '无'} → 版次可能未对齐")
    task.step("baseline", "done", f"PCB ∩ SCH = {len(pcb_refs & sch_refs)}")
    task.set_progress(45)

    if task.cancelled:
        return

    # ---------- 5. 逐条核对 ----------
    task.active("scan", "解析待核对 BOM")
    bom = bom_reader.load_bom(bom_rec["path"])
    task.emit("INFO", f"BOM 明细行 {len(bom.real_lines)} · 父级行 {len(bom.group_rows)} · "
                      f"残缺空行 {len(bom.incomplete_rows)} · 位号 {len(bom.all_refs())} 个")
    last = [0]

    result = checker.run_check(
        sch, pcb, bom, store.master if master_rec else None,
        options=options,
        log=lambda level, text: _log_progress(task, level, text, last),
    )
    for p in result.problems[:80]:
        task.emit("WARN" if p["level"] == "严重" else "INFO",
                  (f"第{p['row']}行：" if p["row"] else "全局：") + f"[{p['kind']}] {p['msg']}")
    task.step("scan", "done", f"明细 {len(bom.real_lines)} 行")
    task.set_progress(75)

    if task.cancelled:
        return

    # ---------- 6. 生成结果 ----------
    task.active("report")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_name = f"{_safe_name(bom_rec['name'])}-BOM核对结果.xlsx"
    out_path = os.path.join(store.outputs_dir, f"{stamp}_{out_name}")
    report.write_report(bom_rec["path"], out_path, result, bom, options)
    task.emit("OK", f"已生成 {out_name}（4 个 Sheet）")

    task.metrics = {
        "total": result.stats["total"],
        "severe": result.stats["severe"],
        "normal": result.stats["normal"],
        "info": result.stats["info"],
        "valueDiff": result.stats["valueDiff"],
        "missing": result.stats["missing"],
        "detailRows": len(bom.real_lines),
        "refCount": len(bom.all_refs()),
        "pcbCount": len(pcb_refs),
        "schCount": len(sch_refs),
        "distribution": result.stats["distribution"],
    }
    task.output = {
        "name": out_name,
        "path": out_path,
        "downloadUrl": f"/api/tasks/{task.id}/download",
    }
    task.result = {
        "kind": "check",
        "meta": {
            "taskId": task.id,
            "title": task.title,
            "createdAt": task.createdAt,
            "files": task.files,
            "masterUsed": bool(master_rec),
        },
        "baseline": result.baseline,
        "metrics": result.stats,
        "distribution": result.stats["distribution"],
        "problems": result.problems,
        "missingRefs": result.missing_refs,
        "unknownRefs": sorted(set(result.unknown_refs), key=altium.ref_sort_key),
        "valueDiffs": result.value_diffs,
        "refTable": result.ref_table,
        "refsFromNote": result.refs_from_note,
        "bom": bom.summary(),
        "rules": [
            {"key": k, "name": n, "level": lv, "desc": d, "enabled": k in set(
                options.get("rules") or [r[0] for r in checker.RULES])}
            for k, n, lv, d in checker.RULES
        ],
    }
    task.step("report", "done", "4 个 Sheet 已写入")
    task.set_progress(100)


def _log_progress(task: jobs.Task, level: str, text: str, last: list[int]) -> None:
    """把引擎日志按节奏推给前端，避免一次性刷屏。"""
    task.emit(level, text)
    if text.startswith("核对完成"):
        return
    current = len(task.logs)
    if current - last[0] >= 6:
        last[0] = current
        task.set_progress(min(74, 45 + current // 3))


def run_generate(store, task: jobs.Task, payload: dict[str, Any]) -> None:
    sel = store.selection
    options = payload.get("options") or {}
    mode = payload.get("mode") or "merge"

    # ---------- 1. 读取文件 ----------
    task.active("read")
    sch_rec = store.get_upload(payload.get("schematicId") or sel.get("schematic"), "schematic")
    pcb_rec = store.get_upload(payload.get("pcbId") or sel.get("pcb"), "pcb")

    master_rec = None
    master_id = payload.get("masterId") or sel.get("master")
    if master_id and master_id in store.uploads and store.uploads[master_id]["status"] == "已解析":
        master_rec = store.uploads[master_id]

    template_entry = store.template_entry(payload.get("templateId") or store.default_template_id)
    task.files = {
        "schematic": {"id": sch_rec["id"], "name": sch_rec["name"], "size": sch_rec["size"]},
        "pcb": {"id": pcb_rec["id"], "name": pcb_rec["name"], "size": pcb_rec["size"]},
        "master": {"id": master_rec["id"], "name": master_rec["name"], "size": master_rec["size"]} if master_rec else None,
        "template": {"id": template_entry["id"], "name": template_entry["name"]} if template_entry else None,
    }
    task.title = payload.get("title") or f"{_safe_name(sch_rec['name'])} BOM 生成"
    task.emit("INFO", f"设计文件：{sch_rec['name']} + {pcb_rec['name']}")
    task.emit("INFO", f"物料总表：{master_rec['name']}" if master_rec else "未上传物料总表：编码将全部留空并标记待确认")
    task.emit("INFO", f"BOM 模板：{template_entry['name']}" if template_entry else "未指定模板：使用内置 9 列模板")
    task.step("read", "done", "输入已加载")
    task.set_progress(10)

    # ---------- 2 / 3. 解析 ----------
    task.active("sch")
    sch = altium.extract_sch(open(sch_rec["path"], "rb").read(), sch_rec["name"])
    task.emit("INFO", f"原理图元件 {len(sch['components'])} 个，Value / Comment 已提取")
    task.step("sch", "done", f"元件 {len(sch['components'])}")
    task.set_progress(25)

    task.active("pcb")
    pcb = altium.extract_pcb(open(pcb_rec["path"], "rb").read(), pcb_rec["name"])
    task.emit("INFO", f"PCB 元件 {pcb['component_count']} 个，PATTERN "
                      f"{len({c['pattern'] for c in pcb['components'] if c['pattern']})} 种")
    task.step("pcb", "done", f"元件 {pcb['component_count']}")
    task.set_progress(40)

    # 解析为空是最容易被当成「BOM 无法生成」的情况，这里说清楚会退化成什么结果
    if not sch.get("components"):
        task.emit("WARN", "原理图未解析出任何元件：将只依据 PCB 的位号与封装生成 BOM，"
                          "规格/型号列为空并标注待确认，请确认上传的是 .SchDoc 且含元件记录")
    if not pcb.get("components"):
        task.emit("WARN", "PCB 未解析出任何元件：封装列会为空，请确认上传的是 .PcbDoc")

    if task.cancelled:
        return

    # ---------- 4. 合并元件 ----------
    task.active("merge")
    components, diffs = generator.build_components(sch, pcb)
    task.emit("INFO", f"按位号关联后得到 {len(components)} 个元件")
    if diffs["onlySchematic"] or diffs["onlyPcb"]:
        task.emit("WARN", f"版次差异：仅原理图 {diffs['onlySchematic']}；仅 PCB {diffs['onlyPcb']}")
    if diffs["unlabeledPcb"]:
        task.emit("WARN", f"PCB 中 {len(diffs['unlabeledPcb'])} 个元件无位号，已列入待确认")
    task.step("merge", "done", f"{len(components)} 个元件")
    task.set_progress(55)

    # ---------- 5. 匹配物料总表 ----------
    task.active("match")
    task.emit("INFO", "规格优先级：Value ＞ Comment ＞ 器件描述；封装优先级：PCB PATTERN ＞ 原理图模型 ＞ 库引用推断")
    result = generator.generate(sch, pcb, store.master if master_rec else None,
                               mode=mode, options=options,
                               log=lambda level, text: task.emit(level, text))
    task.step("match", "done",
              f"确定 {result.stats['determined']} · 候选 {result.stats['candidate']} · 待确认 {result.stats['pending']}")
    task.set_progress(80)

    if task.cancelled:
        return

    # ---------- 6. 写入 BOM ----------
    task.active("write")
    tmpl = (template_mod.inspect_template(template_entry["path"], display_name=template_entry["name"])
            if template_entry else store.current_template())
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_name = f"{_safe_name(sch_rec['name'])}-BOM-{stamp}.xlsx"
    out_path = os.path.join(store.outputs_dir, out_name)
    header_meta = payload.get("headerMeta") or {}

    # 模板损坏 / 合并单元格冲突等一律降级为内置模板，不让 BOM 生成失败
    warning = template_mod.write_bom_with_fallback(tmpl, out_path, result.rows, header_meta)
    used_tmpl = tmpl
    if warning:
        task.emit("WARN", warning)
        used_tmpl = template_mod.builtin_template()
    else:
        task.emit("OK", f"已按模板「{tmpl.name}」生成 {len(result.rows)} 行")

    task.metrics = {
        "componentCount": result.stats["componentCount"],
        "rowCount": result.stats["rowCount"],
        "determined": result.stats["determined"],
        "candidate": result.stats["candidate"],
        "pending": result.stats["pending"],
        "unmatchedRows": result.stats["unmatchedRows"],
        "conflictCount": result.stats["conflictCount"],
        "mode": mode,
    }
    task.output = {"name": out_name, "path": out_path,
                   "downloadUrl": f"/api/tasks/{task.id}/download"}
    task.result = {
        "kind": "generate",
        "meta": {"taskId": task.id, "title": task.title, "createdAt": task.createdAt,
                 "files": task.files, "mode": mode,
                 "template": used_tmpl.summary() if used_tmpl else None,
                 "templateWarning": warning},
        "stats": result.stats,
        "rows": result.rows,
        "components": [
            {k: c[k] for k in ("designator", "libref", "value", "comment", "spec", "specBasis",
                               "footprint", "footprintBasis", "code", "materialName",
                               "materialSpec", "unit", "status", "reason", "conflict",
                               "pins", "layer")}
            for c in result.components
        ],
        "conflicts": result.conflicts,
        "diffs": result.diffs,
        "specRule": generator.RULE_SPEC,
        "footprintRule": generator.RULE_FOOTPRINT,
    }
    task.step("write", "done", f"{len(result.rows)} 行")
    task.set_progress(100)


def _size(num: int) -> str:
    kb = (num or 0) / 1024
    return f"{kb:.1f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"
