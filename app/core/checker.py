"""BOM 三方交叉核对引擎。

基准关系：

    PCB 封装  ─┐
    原理图封装 ├─→ 交叉比对 ─→ 问题清单
    物料总表   ─┘
         ↑
        BOM

九类规则见 ``RULES``。
"""

from __future__ import annotations

from typing import Any, Callable

from . import normalize
from .altium import parse_ref_list, ref_sort_key

LEVEL_ORDER = {"严重": 0, "一般": 1, "提示": 2}

RULES = [
    ("footprint", "封装不符", "严重", "BOM 规格中的封装代号 ≠ PCB 实际 PATTERN"),
    ("name", "名称与总表不符", "严重", "BOM 子项物料名称 ≠ 物料总表同编码名称"),
    ("missing", "位号缺失", "严重", "PCB ∪ 原理图位号 − BOM 位号 ≠ 空集"),
    ("unknown", "位号不存在", "严重", "BOM 位号 −（PCB ∪ 原理图）≠ 空集"),
    ("qty", "用量≠位号数", "严重", "用量分子 ≠ 位置号拆分后的位号个数"),
    ("nocode", "缺物料编码", "严重", "子项物料编码为空"),
    ("badcode", "编码不存在", "严重", "编码在物料总表中查不到"),
    ("format", "位号格式", "一般", "全角逗号 / 分号 / 连续逗号 / 多余空格"),
    ("item", "项次跳号或缺项次", "一般", "项次不连续，或有项次用量但无编码与名称"),
]

ADVICE = {
    "footprint": "以 PCB 实际 PATTERN 与物料编码对应封装为准修正 BOM 规格",
    "name": "按物料总表正式名称回填",
    "missing": "补齐位号并同步核对用量",
    "unknown": "删除该位号或改正为设计文件中的实际位号",
    "qty": "补全同行位号或修正用量",
    "nocode": "在物料总表中检索同规格物料并回填编码",
    "badcode": "确认编码是否正确，或改用物料总表中的有效编码",
    "format": "位号统一使用半角逗号分隔，去除多余空格与空位号",
    "item": "重排项次，保持从 1 连续",
    "disabled": "该物料已禁用，请改用有效物料",
}


class CheckResult:
    def __init__(self) -> None:
        self.problems: list[dict[str, Any]] = []
        self.value_diffs: list[dict[str, Any]] = []
        self.missing_refs: list[dict[str, Any]] = []
        self.unknown_refs: list[str] = []
        self.ref_table: list[dict[str, Any]] = []
        self.refs_from_note: list[dict[str, Any]] = []   # 位置号取自备注列的行
        self.baseline: dict[str, Any] = {}
        self.stats: dict[str, Any] = {}

    def add(self, kind: str, level: str, row: int | None, cols: str, msg: str,
            advice: str | None = None) -> None:
        self.problems.append(
            {
                "kind": kind,
                "level": level,
                "row": row,
                "cols": cols,
                "msg": msg,
                "advice": advice or ADVICE.get(_advice_key(kind), ""),
            }
        )


def _advice_key(kind: str) -> str:
    mapping = {
        "封装不符": "footprint",
        "名称与总表不符": "name",
        "位号缺失": "missing",
        "位号不存在": "unknown",
        "用量≠位号数": "qty",
        "缺物料编码": "nocode",
        "编码不存在": "badcode",
        "位号格式": "format",
        "项次跳号": "item",
        "缺项次": "item",
        "空行(未填写)": "item",
        "物料已禁用": "disabled",
    }
    return mapping.get(kind, "")


def run_check(
    sch: dict[str, Any],
    pcb: dict[str, Any],
    bom,
    master,
    options: dict[str, Any] | None = None,
    log: Callable[[str, str], None] | None = None,
) -> CheckResult:
    """执行核对，返回结构化结果。"""
    opts = options or {}
    enabled = set(opts.get("rules") or [r[0] for r in RULES])
    check_master = bool(master) and opts.get("useMaster", True) and "badcode" in enabled

    def emit(level: str, text: str) -> None:
        if log:
            log(level, text)

    res = CheckResult()

    pcb_des: dict[str, dict[str, Any]] = {}
    for c in pcb.get("components", []):
        if c.get("designator"):
            pcb_des[c["designator"].strip()] = c
    sch_des: dict[str, dict[str, Any]] = {}
    for c in sch.get("components", []):
        if c.get("designator"):
            sch_des[c["designator"].strip()] = c

    # ---------- ④ 基准一致性 ----------
    only_pcb = sorted(set(pcb_des) - set(sch_des), key=ref_sort_key)
    only_sch = sorted(set(sch_des) - set(pcb_des), key=ref_sort_key)
    identical = not only_pcb and not only_sch
    res.baseline = {
        "pcbCount": pcb.get("component_count", len(pcb.get("components", []))),
        "schCount": len(sch.get("components", [])),
        "pcbRefCount": len(pcb_des),
        "schRefCount": len(sch_des),
        "identical": identical,
        "onlyPcb": only_pcb,
        "onlySch": only_sch,
        "unlabeled": [c.get("pattern", "") for c in pcb.get("unlabeled", [])],
        "checked": opts.get("verifyBaseline", True),
    }
    if identical:
        emit("OK", f"基准一致性校验通过：PCB {len(pcb_des)} / 原理图 {len(sch_des)}，位号集合完全一致")
    else:
        emit("WARN", f"基准不一致：仅 PCB 有 {only_pcb or '无'}；仅原理图有 {only_sch or '无'}")

    # ---------- 位置号被填进备注列的情况 ----------
    # 有人填 BOM 时位置号列留空、把位号写进备注，这会让「位号缺失」整片误报。
    # 这里用设计文件里的位号集合做过滤后回填：只有确实存在于 PCB/原理图的位号
    # 才会被采纳，既消掉误报，也不会凭空造出「位号不存在」。
    design_refs = set(pcb_des) | set(sch_des)
    recovered: list[dict[str, Any]] = []
    for line in bom.lines:
        if line["refList"] or not line.get("noteRefs"):
            continue
        hits = [r for r in line["noteRefs"] if r in design_refs]
        if not hits:
            continue
        line["refList"] = hits
        line["refs"] = " ".join(hits)
        line["refsSource"] = "备注"
        recovered.append({"row": line["row"], "refs": hits, "note": line.get("note", "")})

    if recovered:
        res.refs_from_note = recovered
        total = sum(len(item["refs"]) for item in recovered)
        emit("WARN", f"{len(recovered)} 行的位置号为空，但备注列里写有位号："
                     f"已从备注取回 {total} 个位号，不作为位号缺失处理（行 "
                     + "、".join(str(item["row"]) for item in recovered[:8])
                     + ("…" if len(recovered) > 8 else "") + "）")

    bom_refs = bom.all_refs()
    lines = bom.lines

    # ---------- 逐条核对 ----------
    for line in lines:
        r = line["row"]
        label = line["name"] or line["code"] or "—"

        if line["incomplete"]:
            if "item" in enabled:
                res.add("空行(未填写)", "严重", r, "F/G/M",
                        f"有项次/用量（用量={line['qtyRaw'] or '—'}）但无编码/名称/位号 → BOM 行残缺")
            continue

        if not line["item"] and "item" in enabled:
            res.add("缺项次", "一般", r, "E", f"未填写项次（物料：{label}）")

        # 8. 位号格式
        if line["refs"] and "format" in enabled:
            if normalize.has_bad_separator(line["refs"]):
                res.add("位号格式", "一般", r, "M", f"位号含全角/非法分隔符 → {line['refs']!r}")
            if normalize.has_empty_ref(line["refs"]):
                res.add("位号格式", "一般", r, "M", f"位号列表有连续逗号（空位号）→ {line['refs']!r}")

        # 5. 用量 ≠ 位号数
        if line["refList"] and line["qty"] is not None and "qty" in enabled:
            q = int(line["qty"])
            if q != len(line["refList"]):
                res.add("用量≠位号数", "严重", r, "J·M",
                        f"用量={q}，但位置号只列出 {len(line['refList'])} 个（{line['refs']}）")

        # 6 / 7. 物料编码
        mat = None
        if not line["code"]:
            if "nocode" in enabled:
                hint = _suggest_code(master, line, pcb_des) if check_master else ""
                res.add("缺物料编码", "严重", r, "F",
                        f"未填写子项物料编码（{label}）",
                        f"总表对应编码为 {hint}" if hint else None)
        elif check_master:
            mat = master.get(line["code"])
            if mat is None:
                res.add("编码不存在", "严重", r, "F",
                        f"物料编码 {line['code']} 在物料总表中查无此编码")
            else:
                # 2. 名称与总表不符
                if line["name"] and mat["name"] and "name" in enabled:
                    if line["name"].strip() != mat["name"].strip():
                        res.add("名称与总表不符", "严重", r, "G",
                                f"BOM 名称「{line['name']}」≠ 总表【{line['code']}】名称「{mat['name']}」")
                if mat["disabled"]:
                    res.add("物料已禁用", "提示", r, "F",
                            f"物料 {line['code']}（{mat['name']}）已禁用")

        # 1. 封装不符
        if "footprint" in enabled:
            _check_footprint(res, line, pcb_des, master, mat)

        # 4. 位号不存在
        if "unknown" in enabled:
            for ref in line["refList"]:
                if ref not in pcb_des and ref not in sch_des:
                    res.add("位号不存在", "严重", r, "M",
                            f"位号 {ref} 在 PCB/原理图中不存在（多余位号或书写错误）")
                    res.unknown_refs.append(ref)

    # 3. 位号缺失
    if "missing" in enabled:
        for ref in sorted((set(pcb_des) | set(sch_des)) - bom_refs, key=ref_sort_key):
            pc = pcb_des.get(ref, {})
            sc = sch_des.get(ref, {})
            pat = pc.get("pattern", "") or sc.get("footprint", "")
            val = sc.get("spec", "") or sc.get("comment", "")
            res.add("位号缺失", "严重", None, "M",
                    f"PCB/原理图有 {ref}（封装 {pat or '—'} / 值 {val or '—'}），BOM 未列 → 漏项")
            res.missing_refs.append(
                {"ref": ref, "footprint": pat or "—(PCB 中无位号)", "value": val or "—"}
            )

    # 9. 项次跳号
    if "item" in enabled:
        seen = sorted({int(float(l["item"])) for l in lines if _is_num(l["item"])})
        for a, b in zip(seen, seen[1:]):
            if b != a + 1:
                res.add("项次跳号", "一般", None, "E",
                        f"项次不连续：{a} → {b}（缺少项次 {a + 1}）")

    # ---------- 值比对（需确认，不判严重） ----------
    res.value_diffs = _value_diffs(lines, sch_des, bom)

    # ---------- 位号对照表 ----------
    all_refs = sorted(set(pcb_des) | set(sch_des) | bom_refs, key=ref_sort_key)
    for ref in all_refs:
        in_bom = ref in bom_refs
        pc = pcb_des.get(ref, {})
        sc = sch_des.get(ref, {})
        if in_bom and (ref in pcb_des or ref in sch_des):
            conclusion = "一致"
        elif in_bom:
            conclusion = "★ BOM 多出该位号"
        else:
            conclusion = "★ BOM 缺失该位号"
        res.ref_table.append(
            {
                "ref": ref,
                "pcbFootprint": pc.get("pattern", "—(PCB 中无位号)") if pc else "—(PCB 中无)",
                "schValue": sc.get("spec", "") if sc else "",
                "inBom": in_bom,
                "conclusion": conclusion,
            }
        )

    res.value_diffs = sorted(res.value_diffs, key=lambda d: ref_sort_key(d["refs"].split(" ")[0]))

    # ---------- 统计 ----------
    res.problems.sort(key=lambda p: (LEVEL_ORDER.get(p["level"], 3), p["row"] is None, p["row"] or 0))
    for i, p in enumerate(res.problems, start=1):
        p["no"] = i

    dist: dict[str, dict[str, Any]] = {}
    for p in res.problems:
        d = dist.setdefault(p["kind"], {"kind": p["kind"], "level": p["level"], "count": 0})
        d["count"] += 1
    total = len(res.problems) or 1
    res.stats = {
        "total": len(res.problems),
        "severe": sum(1 for p in res.problems if p["level"] == "严重"),
        "normal": sum(1 for p in res.problems if p["level"] == "一般"),
        "info": sum(1 for p in res.problems if p["level"] == "提示"),
        "valueDiff": len(res.value_diffs),
        "missing": len(res.missing_refs),
        "refsFromNote": len(res.refs_from_note),
        "distribution": [
            {
                "kind": d["kind"],
                "level": d["level"],
                "count": d["count"],
                "pct": round(d["count"] * 100 / total),
            }
            for d in sorted(
                dist.values(),
                key=lambda d: (LEVEL_ORDER.get(d["level"], 3), -d["count"]),
            )
        ],
    }

    emit("OK", f"核对完成：共 {res.stats['total']} 项问题（严重 {res.stats['severe']} / 一般 {res.stats['normal']}）"
               f" + {res.stats['valueDiff']} 条值差异待确认")
    return res


def _check_footprint(res: CheckResult, line: dict[str, Any], pcb_des: dict[str, Any], master, mat) -> None:
    """规则 1：封装不符。判定以 PCB PATTERN 为基准，并用物料编码的规格做交叉印证。"""
    bom_fp = normalize.extract_footprint(line["name"], line["spec"])
    if not bom_fp:
        return
    matched_refs = [r for r in line["refList"] if r in pcb_des]
    if not matched_refs:
        return
    patterns = {pcb_des[r].get("pattern", "").strip().upper() for r in matched_refs}
    patterns.discard("")
    if not patterns or bom_fp in patterns:
        return

    cache_pat = ",".join(sorted(patterns))
    code_pat = ""
    if mat is not None:
        code_pat = normalize.extract_footprint(mat["spec"], mat["name"])
        if code_pat == bom_fp:
            # BOM 名称与编码一致、仅 PCB 不同 → 属于设计文件与 BOM 版次差异，降为一般
            res.add("封装不符", "一般", line["row"], "G·H",
                    f"位号 {'、'.join(matched_refs[:6])}：BOM/编码均为 {bom_fp}，但 PCB PATTERN 为 {cache_pat}"
                    f"（请确认设计与 BOM 版次）")
            return

    evidence = f"PCB 封装 {cache_pat}"
    if code_pat:
        evidence += f"，编码 {line['code']} 对应 {code_pat}"
    res.add("封装不符", "严重", line["row"], "G·H",
            f"位号 {'、'.join(matched_refs[:6])}：BOM 规格 {bom_fp} ≠ {evidence}")


def _value_diffs(lines: list[dict[str, Any]], sch_des: dict[str, Any], bom) -> list[dict[str, Any]]:
    """值比对：BOM 声明值与原理图标注值的差异，仅作提示。"""
    out: list[dict[str, Any]] = []
    for line in lines:
        if line["incomplete"] or not line["refList"]:
            continue
        declared = _declared_value(line)
        if not declared:
            continue
        refs = [r for r in line["refList"] if r in sch_des]
        if not refs:
            continue
        groups: dict[str, list[str]] = {}
        for r in refs:
            sv = sch_des[r].get("spec", "") or sch_des[r].get("comment", "")
            if not sv:
                continue
            key = "一致" if normalize.values_equivalent(declared, sv) else f"≠{sv}"
            groups.setdefault(key, []).append(r)
        for key, group in groups.items():
            equivalent = key == "一致"
            sample = sch_des[group[0]].get("spec", "") or sch_des[group[0]].get("comment", "")
            out.append(
                {
                    "refs": " ".join(sorted(group, key=ref_sort_key)),
                    "bom": declared,
                    "sch": sample,
                    "equivalent": equivalent,
                    "note": "" if equivalent else "BOM 声明值与原理图标注值不同，请确认是否改版",
                }
            )
    return out


def _declared_value(line: dict[str, Any]) -> str:
    """从 BOM 名称/规格里取出声明的阻容值。"""
    import re

    for text in (line["spec"], line["name"]):
        for token in re.split(r"[\s,，/]+", str(text or "")):
            t = token.strip()
            if t and normalize.is_value_like(t):
                return t
    return ""


def _suggest_code(master, line: dict[str, Any], pcb_des: dict[str, Any]) -> str:
    if not master:
        return ""
    footprint = ""
    for r in line["refList"]:
        if r in pcb_des:
            footprint = pcb_des[r].get("pattern", "")
            break
    cands = master.candidates(line["spec"] or line["name"], footprint)
    if cands:
        return cands[0]["code"]
    return ""


def _is_num(value: Any) -> bool:
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def problem_rows(result: CheckResult) -> dict[int, list[dict[str, Any]]]:
    """按 BOM 行号聚合问题，供 Excel 高亮与行内说明使用。"""
    by_row: dict[int, list[dict[str, Any]]] = {}
    for p in result.problems:
        if p["row"]:
            by_row.setdefault(p["row"], []).append(p)
    return by_row


def parse_cols(cols: str) -> list[str]:
    return [c.strip() for c in str(cols or "").replace("·", "/").split("/") if c.strip()]


def ref_keys(refs: str) -> list[str]:
    return parse_ref_list(refs)
