"""物料总表（ERP 导出）加载、检索与候选匹配。"""

from __future__ import annotations

from typing import Any

from . import normalize
from .sheets import find_header_row, load_rows, match_column, text_of

HEADER_KEYS = [
    "物料编码", "物料名称", "规格型号", "数据状态", "禁用", "基本单位", "库存位置",
]

# 与 Skill 6.3 一致的兜底列号（1 基），仅在表头匹配失败时使用
FALLBACK = {"code": 2, "name": 3, "spec": 4, "status": 6, "disabled": 7, "attr": 8, "unit": 9}

DISABLED_TRUE = {"是", "Y", "YES", "TRUE", "1", "已禁用", "停用"}


class MaterialMaster:
    def __init__(self, entries: dict[str, dict[str, Any]], columns: dict[str, int],
                 header: list[str], source: str, invalid_status: int):
        self.entries = entries
        self.columns = columns
        self.header = header
        self.source = source
        self.invalid_status = invalid_status

    # -- 统计 ---------------------------------------------------------------
    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def disabled_count(self) -> int:
        return sum(1 for e in self.entries.values() if e["disabled"])

    @property
    def valid_count(self) -> int:
        return self.count - self.disabled_count

    def get(self, code: str) -> dict[str, Any] | None:
        return self.entries.get(str(code or "").strip())

    def is_disabled(self, code: str) -> bool:
        e = self.get(code)
        return bool(e and e["disabled"])

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "count": self.count,
            "valid": self.valid_count,
            "disabled": self.disabled_count,
            "header": self.header,
            "columns": self.columns,
        }

    # -- 匹配 ---------------------------------------------------------------
    def value_match(self, entry: dict[str, Any], spec: str) -> str:
        """判断 BOM 规格值与总表条目的匹配强度。

        返回 ``"exact"``（完全一致，或能在名称里定位到该值）/
        ``"equivalent"``（等价写法）/ ``""``（对不上）。
        调用方据此决定是判「确定」还是「候选」。
        """
        target = normalize.normalize_value(spec)
        if not target:
            return ""

        values = {normalize.normalize_value(entry["spec"])}
        for token in _value_tokens(entry["name"]):
            values.add(normalize.normalize_value(token))
        values.discard("")
        if target in values:
            return "exact"
        if any(normalize.values_equivalent(target, v) for v in values):
            return "equivalent"

        # 规格型号列为空时（ERP 导出很常见），规格只写在名称里：
        # 例如「直插电阻1/16W-120K±5％-P」里的 120K。
        if name_contains_value(entry["name"], normalize.value_aliases(spec)):
            return "exact"
        return ""

    def candidates(self, spec: str, footprint: str = "", category: str = "",
                   limit: int = 8) -> list[dict[str, Any]]:
        """按「归一化规格值 + 封装」给出候选物料，顺序即置信度。

        ⚠️ 规格值无法判定时**一律不返回候选**：只靠封装匹配的话，任何 0603 的
        元件都会命中一大堆互不相关的物料，按编码排序后必然给出错误编码——
        宁可不给候选，让人工指定，也不能给一个看起来像对的错误编码。
        """
        if not normalize.normalize_value(spec):
            return []

        fp = (footprint or "").upper()
        # 设计端常写厂家/自定义封装名（CAP-TH_BD10.0-P5.00-D0.6-FD、0603_C…），
        # 只有能抽出代号时才参与封装过滤，否则只按规格值匹配。
        design_fp = normalize.extract_footprint(fp)
        scored: list[tuple[int, dict[str, Any]]] = []

        for e in self.entries.values():
            if e["disabled"]:
                continue
            score = 0
            haystack = f"{e['name']} {e['spec']}"
            e_fp = normalize.extract_footprint(haystack)
            kind = self.value_match(e, spec)
            if kind == "exact":
                score += 6
            elif kind == "equivalent":
                score += 3
            else:
                continue
            if design_fp:
                if e_fp == design_fp:
                    score += 4
                elif e_fp:
                    continue          # 双方代号都识别得出且不同 → 真的封装不符
                else:
                    score += 1        # 总表规格里没写代号，无从比对，只给基础分
            if category and category.upper() in haystack.upper():
                score += 2
            scored.append((score, e))

        scored.sort(key=lambda x: (-x[0], x[1]["code"]))
        return [e for _, e in scored[:limit]]

    def search(self, query: str, status: str = "all", limit: int = 200) -> list[dict[str, Any]]:
        q = (query or "").strip().upper()
        out = []
        for e in self.entries.values():
            if status == "valid" and e["disabled"]:
                continue
            if status == "disabled" and not e["disabled"]:
                continue
            if q and q not in f"{e['code']} {e['name']} {e['spec']}".upper():
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out


_VALUE_CHARS = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.")


def _is_value_char(ch: str) -> bool:
    """判断字符是否属于「规格值的一部分」。

    只认 ASCII 字母数字与小数点：中文名里「贴片电容0.1uF」的值紧跟汉字，
    若把汉字也算进边界，边界校验会误杀正常匹配。
    """
    return ch in _VALUE_CHARS


def name_contains_value(name: str, needles: set[str]) -> bool:
    """在物料名称中查找规格值，并做边界校验。

    ERP 导出的物料总表常常「规格型号列为空、规格只写在名称里」，
    例如 ``直插电阻1/16W-120K±5％-P`` 里的 120K。
    边界校验不能省：否则 2K 会命中 22K、20K 会命中 120K。
    """
    hay = str(name or "").upper().replace(" ", "")
    if not hay or not needles:
        return False
    for needle in needles:
        if not needle:
            continue
        start = 0
        while True:
            i = hay.find(needle, start)
            if i < 0:
                break
            before = hay[i - 1] if i > 0 else " "
            after = hay[i + len(needle)] if i + len(needle) < len(hay) else " "
            if not (_is_value_char(before) or _is_value_char(after)):
                return True
            start = i + 1
    return False


def _value_tokens(name: str) -> list[str]:
    import re

    return [t for t in re.split(r"[\s,，/]+", str(name or "")) if t]


def load_master(path: str) -> MaterialMaster:
    rows, _ = load_rows(path)
    if not rows:
        raise ValueError("物料总表为空")

    hdr_idx = find_header_row(rows, HEADER_KEYS)  # 1 基
    header = [text_of(v) for v in (rows[hdr_idx - 1] if hdr_idx <= len(rows) else [])]

    columns = {
        "code": match_column(header, "物料编码", "子项物料编码", "物料编号", "编码") or FALLBACK["code"],
        # ERP 导出常用简写表头「名称」，必须认；漏了它会退回兜底列号，
        # 换一份列顺序不同的表就会把名称读成空，进而一条都匹配不上。
        "name": match_column(header, "物料名称", "子项物料名称", "品名", "名称") or FALLBACK["name"],
        "spec": match_column(header, "规格型号", "规格", "型号") or FALLBACK["spec"],
        "status": match_column(header, "数据状态", "状态") or FALLBACK["status"],
        "disabled": match_column(header, "禁用状态", "禁用", "是否禁用") or FALLBACK["disabled"],
        "attr": match_column(header, "物料属性", "属性") or FALLBACK["attr"],
        "unit": match_column(header, "基本单位", "单位") or FALLBACK["unit"],
        "location": match_column(header, "库存位置", "库位") or 0,
    }

    entries: dict[str, dict[str, Any]] = {}
    invalid = 0
    for row in rows[hdr_idx:]:
        code = text_of(row[columns["code"] - 1]) if len(row) >= columns["code"] else ""
        if not code:
            continue
        flag = ""
        if columns.get("disabled") and len(row) >= columns["disabled"]:
            flag = text_of(row[columns["disabled"] - 1])
        disabled = flag.upper() in DISABLED_TRUE
        status = text_of(row[columns["status"] - 1]) if len(row) >= columns["status"] else ""
        entry = {
            "code": code,
            "name": text_of(row[columns["name"] - 1]) if len(row) >= columns["name"] else "",
            "spec": text_of(row[columns["spec"] - 1]) if len(row) >= columns["spec"] else "",
            "status": status,
            "disabled": disabled,
            "disabledRaw": flag,
            "attr": text_of(row[columns["attr"] - 1]) if columns.get("attr") and len(row) >= columns["attr"] else "",
            "unit": text_of(row[columns["unit"] - 1]) if columns.get("unit") and len(row) >= columns["unit"] else "PCS",
            "location": text_of(row[columns["location"] - 1]) if columns.get("location") and len(row) >= columns["location"] else "",
        }
        if not entry["unit"]:
            entry["unit"] = "PCS"
        if entry["disabled"]:
            invalid += 1
        entries[code] = entry

    return MaterialMaster(entries, columns, header, path, invalid)
