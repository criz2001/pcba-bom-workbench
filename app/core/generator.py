"""BOM 生成引擎。

规格取值优先级：原理图 Value ＞ Comment ＞ 描述 / 库引用。
封装取值优先级：PCB 实际 PATTERN ＞ 原理图 PCB 模型 ＞ 库引用推断。
未匹配项仍然保留在 BOM 中并标记「待确认」，不强行匹配。
"""

from __future__ import annotations

from typing import Any, Callable

from . import normalize
from .altium import ref_sort_key

RULE_SPEC = ["原理图 Value", "原理图 Comment", "器件描述 / 库引用"]
RULE_FOOTPRINT = ["PCB 实际 PATTERN", "原理图 PCB 模型", "库引用推断"]


class GenerateResult:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.components: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []
        self.diffs: list[dict[str, Any]] = []
        self.stats: dict[str, Any] = {}


def build_components(sch: dict[str, Any], pcb: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """合并原理图与 PCB 元件，记录两者差异。"""
    sch_map: dict[str, dict[str, Any]] = {
        c["designator"].strip(): c for c in sch.get("components", []) if c.get("designator")
    }
    pcb_map: dict[str, dict[str, Any]] = {
        c["designator"].strip(): c for c in pcb.get("components", []) if c.get("designator")
    }

    only_sch = sorted(set(sch_map) - set(pcb_map), key=ref_sort_key)
    only_pcb = sorted(set(pcb_map) - set(sch_map), key=ref_sort_key)
    unlabeled_pcb = pcb.get("unlabeled", [])

    merged: list[dict[str, Any]] = []
    for ref in sorted(set(sch_map) | set(pcb_map), key=ref_sort_key):
        s = sch_map.get(ref, {})
        p = pcb_map.get(ref, {})

        value = (s.get("value") or "").strip()
        comment = (s.get("comment") or "").strip()
        description = (s.get("description") or "").strip()
        libref = (s.get("libref") or "").strip()

        if value:
            spec, basis = value, RULE_SPEC[0]
        elif comment:
            spec, basis = comment, RULE_SPEC[1]
        else:
            spec, basis = description or libref, RULE_SPEC[2]

        pcb_pattern = (p.get("pattern") or "").strip()
        sch_footprint = (s.get("footprint") or "").strip()
        if pcb_pattern:
            footprint, fp_basis = pcb_pattern, RULE_FOOTPRINT[0]
        elif sch_footprint:
            footprint, fp_basis = sch_footprint, RULE_FOOTPRINT[1]
        else:
            footprint, fp_basis = normalize.extract_footprint(libref, spec, description), RULE_FOOTPRINT[2]

        conflict = ""
        if value and comment and value.upper() != comment.upper():
            conflict = f"按 Value={value}；Comment={comment} 为旧字段"

        merged.append(
            {
                "designator": ref,
                "libref": libref,
                "value": value,
                "comment": comment,
                "description": description,
                "spec": spec,
                "specBasis": basis,
                "footprint": footprint,
                "footprintBasis": fp_basis,
                "pcbPattern": pcb_pattern,
                "schFootprint": sch_footprint,
                "conflict": conflict,
                "pins": s.get("pins", 0),
                "layer": p.get("layer", ""),
                "onlyPcb": ref in only_pcb,
                "onlySch": ref in only_sch,
            }
        )

    diffs = {
        "onlySchematic": only_sch,
        "onlyPcb": only_pcb,
        "unlabeledPcb": [
            {"pattern": c.get("pattern", ""), "libref": c.get("libref", "")} for c in unlabeled_pcb
        ],
    }
    return merged, diffs


def match_material(component: dict[str, Any], master) -> dict[str, Any]:
    """为单个元件匹配物料编码，返回匹配状态与依据。"""
    out = {"status": "待确认", "code": "", "materialName": "", "materialSpec": "", "unit": "PCS",
           "candidates": [], "reason": ""}
    if master is None:
        out["reason"] = "未提供物料总表，无法匹配编码"
        return out

    spec = component["spec"]
    footprint = component["footprint"]

    # 1. 明确型号或物料号完全匹配
    exact = master.entries.get(spec)
    if exact is not None:
        return _hit(out, exact, "确定", f"规格与物料编码完全一致")

    # 2. 没有可比对的规格值就不能匹配。
    #    以前这种情况会退化成「只按封装匹配」，结果任意 0603 元件都被塞上总表里
    #    编码最小的一条物料——错得看起来还挺像对的，比不给编码更危险。
    if not normalize.normalize_value(spec):
        out["reason"] = ("设计文件中该元件没有可用规格值（Value / Comment 为空），"
                         "无法在物料总表中匹配，请人工指定编码或补全原理图属性")
        return out

    # 3. 规格值 + 封装一起匹配
    cands = master.candidates(spec, footprint, limit=8)
    if not cands:
        # 规格对得上但封装对不上时，candidates() 会把它们过滤掉。
        # 这里忽略封装再查一次，把「封装不符」讲清楚，而不是笼统地说没候选。
        same_value = master.candidates(spec, "", limit=5)
        if same_value:
            out["candidates"] = [
                {"code": c["code"], "name": c["name"], "spec": c["spec"], "disabled": c["disabled"]}
                for c in same_value
            ]
            shown = "、".join(f"{c['spec'] or c['name']}（{c['code']}）" for c in same_value[:3])
            out["reason"] = (f"物料总表中有同规格物料，但封装不符"
                             f"（设计封装 {footprint or '未知'}）：{shown}，请确认封装或改用正确编码")
        else:
            out["reason"] = "物料总表中无同规格物料，保留设计规格并标记待确认"
        return out

    top = cands[0]
    out["candidates"] = [
        {"code": c["code"], "name": c["name"], "spec": c["spec"], "disabled": c["disabled"]}
        for c in cands[:5]
    ]
    value_kind = master.value_match(top, spec)
    design_fp = normalize.extract_footprint(footprint)
    master_fp = normalize.extract_footprint(top["spec"], top["name"])

    # 3.1 两侧封装代号都能识别且一致
    if design_fp and master_fp and design_fp == master_fp:
        unique = [
            c for c in cands
            if normalize.extract_footprint(c["spec"], c["name"]) == design_fp
            and master.value_match(c, spec) == "exact"
        ]
        if len(unique) == 1:
            return _hit(out, unique[0], "确定", f"规格值与封装 {design_fp} 唯一匹配")
        return _hit(out, top, "候选",
                    f"规格值与封装 {design_fp} 匹配，但总表中有 {len(unique)} 条"
                    f"同规格同封装物料，请复核编码")

    # 3.2 封装只有一侧能识别：设计端写厂家封装名，或总表规格里不写封装代号。
    #     这种「没法比对」不等于「冲突」，按规格值给候选、请人复核封装即可。
    if not footprint:
        reason = "规格值匹配，但设计端没有封装信息，请复核封装"
    elif not master_fp:
        reason = (f"规格值匹配，物料总表规格中未标注封装代号"
                  f"（设计封装 {footprint}），请复核封装")
    else:
        reason = (f"规格值匹配，但设计端封装为厂家命名（{footprint}），"
                  f"无法与总表封装自动比对，请复核")
    if value_kind == "equivalent":
        reason = "规格值按等价写法匹配（非完全一致），" + reason
    return _hit(out, top, "候选", reason)


def _hit(out: dict[str, Any], material: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    out.update(
        {
            "status": status,
            "code": material["code"],
            "materialName": material["name"],
            "materialSpec": material["spec"],
            "unit": material.get("unit") or "PCS",
            "reason": reason,
            "disabled": material.get("disabled", False),
        }
    )
    return out


def match_all(components: list[dict[str, Any]], master) -> list[dict[str, Any]]:
    """为每个元件补齐匹配字段。

    无论有没有物料总表都要走一遍：即便匹配不上，也必须保留元件并标记「待确认」，
    而不是让它从 BOM 里消失。单个元件数据异常也只影响它自己，不影响整份 BOM。
    """
    for comp in components:
        try:
            comp.update(match_material(comp, master))
        except Exception as exc:  # 脏数据不该让「BOM 无法生成」
            comp.setdefault("status", "待确认")
            comp.setdefault("code", "")
            comp.setdefault("materialName", "")
            comp.setdefault("materialSpec", "")
            comp.setdefault("unit", "PCS")
            comp.setdefault("candidates", [])
            comp["status"] = "待确认"
            comp["reason"] = f"匹配该元件时出错（{exc}），已保留并标记待确认"
    return components


def rows_for(components: list[dict[str, Any]], mode: str = "merge") -> list[dict[str, Any]]:
    return (
        [_row_per_ref(i, c) for i, c in enumerate(components, start=1)]
        if mode == "perRef"
        else _rows_merged(components)
    )


def generate(
    sch: dict[str, Any],
    pcb: dict[str, Any],
    master,
    mode: str = "merge",
    options: dict[str, Any] | None = None,
    log: Callable[[str, str], None] | None = None,
) -> GenerateResult:
    opts = options or {}

    def emit(level: str, text: str) -> None:
        if log:
            log(level, text)

    res = GenerateResult()
    merged, diffs = build_components(sch, pcb)
    res.diffs = diffs
    emit("INFO", f"原理图 {len([c for c in sch.get('components', [])])} 个元件，"
                 f"PCB {pcb.get('component_count', 0)} 个元件，合并后 {len(merged)} 个位号")

    if not merged:
        raise ValueError(
            "未能从设计文件中解析出任何元件，无法生成 BOM。"
            "请确认原理图为 Altium .SchDoc（二进制或 ASCII 均可）且包含元件记录。"
        )

    if diffs["onlyPcb"] or diffs["onlySchematic"]:
        emit("WARN", f"版次差异：仅原理图有 {len(diffs['onlySchematic'])} 个、仅 PCB 有 {len(diffs['onlyPcb'])} 个位号，"
                     f"已单独列出，不会静默丢弃")
    if diffs["unlabeledPcb"]:
        emit("WARN", f"PCB 中有 {len(diffs['unlabeledPcb'])} 个元件没有位号，已列出待确认")

    resolved = match_all(merged, master)
    for comp in resolved:
        if comp["conflict"]:
            res.conflicts.append(
                {"ref": comp["designator"], "value": comp["value"],
                 "comment": comp["comment"], "note": comp["conflict"]}
            )
            emit("WARN", f"{comp['designator']}：Value={comp['value']} 与 Comment={comp['comment']} 冲突，已按 Value 取值")
        if comp["status"] == "待确认":
            emit("WARN", f"{comp['designator']}（{comp['spec'] or comp['libref'] or '规格未知'}）"
                         f"未匹配到物料编码，已保留在 BOM 中并标注待确认")

    res.components = resolved
    res.rows = rows_for(resolved, mode)

    determined = sum(1 for c in resolved if c["status"] == "确定")
    candidate = sum(1 for c in resolved if c["status"] == "候选")
    pending = sum(1 for c in resolved if c["status"] == "待确认")
    res.stats = {
        "componentCount": len(resolved),
        "rowCount": len(res.rows),
        "determined": determined,
        "candidate": candidate,
        "pending": pending,
        "unmatchedRows": sum(1 for r in res.rows if r["pending"]),
        "conflictCount": len(res.conflicts),
        "mode": mode,
        "specRule": RULE_SPEC,
        "footprintRule": RULE_FOOTPRINT,
        "onlySchematic": diffs["onlySchematic"],
        "onlyPcb": diffs["onlyPcb"],
        "unlabeledPcb": diffs["unlabeledPcb"],
    }
    if pending:
        emit("OK", f"生成完成：{len(res.rows)} 行，其中 {pending} 个元件未匹配到编码，"
                   f"已输出并在「备注」列标注待确认")
    else:
        emit("OK", f"生成完成：{len(res.rows)} 行 · 确定 {determined} / 候选 {candidate}")
    return res


def _display_name(comp: dict[str, Any]) -> str:
    """物料名称回退链：总表名称 → 设计规格 → 库引用 → 描述 → 位号。

    未匹配物料也必须有一行可读的名字，不能留空。
    """
    for key in ("materialName", "spec", "libref", "description"):
        value = (comp.get(key) or "").strip()
        if value:
            return value
    return comp.get("designator", "")


def _display_spec(comp: dict[str, Any]) -> str:
    return (comp.get("materialSpec") or comp.get("spec") or comp.get("libref") or "").strip()


def _rows_merged(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按「规格 + 封装 + 编码」合并为一行，汇总数量与位号。"""
    groups: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for c in components:
        key = (
            normalize.normalize_value(c["spec"]),
            (c["footprint"] or "").upper(),
            c["code"] or f"?{c['designator']}",
            c["status"],
        )
        if key not in groups:
            groups[key] = {
                "code": c["code"],
                "name": _display_name(c),
                "spec": _display_spec(c),
                "unit": c["unit"] or "PCS",
                "qty": 0,
                "refs": [],
                "notes": set(),
                "status": c["status"],
                "designSpec": c["spec"],
                "footprint": c["footprint"],
                "specBasis": c["specBasis"],
                "footprintBasis": c["footprintBasis"],
            }
            order.append(key)
        g = groups[key]
        g["qty"] += 1
        g["refs"].append(c["designator"])
        if c["conflict"]:
            g["notes"].add(f"{c['designator']}：{c['conflict']}")
        if c["reason"] and c["status"] != "确定":
            g["notes"].add(c["reason"])
        if c["status"] == "待确认":
            g["status"] = "待确认"
        elif c["status"] == "候选" and g["status"] != "待确认":
            g["status"] = "候选"
        if c.get("disabled"):
            g["notes"].add(f"物料 {c['code']} 已禁用")

    rows: list[dict[str, Any]] = []
    for i, key in enumerate(order, start=1):
        g = groups[key]
        refs = sorted(set(g["refs"]), key=ref_sort_key)
        pending = g["status"] != "确定"
        note_parts = []
        if g["status"] == "待确认":
            note_parts.append("★待确认：未匹配到物料编码，需人工指定")
        elif g["status"] == "候选":
            note_parts.append("★待确认：编码为候选匹配，请复核")
        note_parts.extend(sorted(g["notes"]))
        rows.append(
            {
                "item": i,
                "code": g["code"],
                "name": g["name"],
                "spec": g["spec"],
                "unit": g["unit"],
                "qty": len(refs),
                "denom": 1,
                "refs": " ".join(refs),
                "note": "；".join(note_parts),
                "pending": pending,
                "unmatched": g["status"] == "待确认",
                "status": g["status"],
                "designSpec": g["designSpec"],
                "footprint": g["footprint"],
                "specBasis": g["specBasis"],
                "footprintBasis": g["footprintBasis"],
            }
        )
    return rows


def _row_per_ref(index: int, c: dict[str, Any]) -> dict[str, Any]:
    pending = c["status"] != "确定"
    notes = []
    if c["status"] == "待确认":
        notes.append("★待确认：未匹配到物料编码，需人工指定")
    elif c["status"] == "候选":
        notes.append("★待确认：编码为候选匹配，请复核")
    if c["conflict"]:
        notes.append(c["conflict"])
    if c["reason"]:
        notes.append(c["reason"])
    return {
        "item": index,
        "code": c["code"],
        "name": _display_name(c),
        "spec": _display_spec(c),
        "unit": c["unit"] or "PCS",
        "qty": 1,
        "denom": 1,
        "refs": c["designator"],
        "note": "；".join(dict.fromkeys(notes)),
        "pending": pending,
        "unmatched": c["status"] == "待确认",
        "status": c["status"],
        "designSpec": c["spec"],
        "footprint": c["footprint"],
        "specBasis": c["specBasis"],
        "footprintBasis": c["footprintBasis"],
    }


def preview_rows(components: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    return [
        {
            "ref": c["designator"],
            "libref": c["libref"],
            "value": c["value"],
            "comment": c["comment"],
            "footprint": c["footprint"],
            "spec": _display_spec(c) or c["spec"],
            "specBasis": c["specBasis"],
            "footprintBasis": c["footprintBasis"],
            "status": c.get("status", "待确认"),
            "code": c.get("code", ""),
            "conflict": c["conflict"],
        }
        for c in components[:limit]
    ]


def preview(sch: dict[str, Any], pcb: dict[str, Any], master, limit: int = 200) -> dict[str, Any]:
    """生成准备页的提取预览。

    关键点：**无论有没有物料总表**，都要走一遍匹配，让每个元件都带上
    status / code 等字段，否则后续按行汇总会因为缺字段直接报错。
    """
    components, diffs = build_components(sch, pcb)
    match_all(components, master)

    determined = sum(1 for c in components if c["status"] == "确定")
    candidate = sum(1 for c in components if c["status"] == "候选")
    pending = sum(1 for c in components if c["status"] == "待确认")

    return {
        "preview": preview_rows(components, limit=limit),
        "componentCount": len(components),
        "mergeRowCount": len(_rows_merged(components)),
        "perRefRowCount": len(components),
        "counts": {"determined": determined, "candidate": candidate, "pending": pending},
        "diffs": diffs,
        "specRule": RULE_SPEC,
        "footprintRule": RULE_FOOTPRINT,
        "masterReady": master is not None,
    }
