"""待核对 BOM 的读取与列映射。"""

from __future__ import annotations

from typing import Any

from . import normalize
from .sheets import find_header_row, load_rows, match_column, text_of

HEADER_KEYS = [
    "项次", "子项物料编码", "子项物料名称", "子项规格型号", "用量", "位置号", "备注",
]

# 与 Skill 6.4 一致的兜底列号（1 基）：E F G J M
FALLBACK = {"item": 5, "code": 6, "name": 7, "spec": 8, "qty": 10, "refs": 13, "note": 14}


class BomFile:
    def __init__(self, rows: list[list[Any]], columns: dict[str, int], header: list[str],
                 header_row: int, source: str):
        self.rows = rows
        self.columns = columns
        self.header = header
        self.header_row = header_row
        self.source = source
        self.lines: list[dict[str, Any]] = []
        self.incomplete_rows: list[int] = []
        self.group_rows: list[int] = []
        self.note_ref_rows: list[int] = []      # 位置号为空、备注里疑似写了位号的行
        self._parse()

    # -- 解析 ---------------------------------------------------------------
    def _cell(self, row: list[Any], key: str) -> str:
        idx = self.columns.get(key) or 0
        if idx < 1 or len(row) < idx:
            return ""
        return text_of(row[idx - 1])

    def _parse(self) -> None:
        c = self.columns
        for r in range(self.header_row + 1, len(self.rows) + 1):
            row = self.rows[r - 1]
            if not any(v is not None and text_of(v) != "" for v in row):
                continue
            item = self._cell(row, "item")
            code = self._cell(row, "code")
            name = self._cell(row, "name")
            spec = self._cell(row, "spec")
            refs = self._cell(row, "refs")
            note = self._cell(row, "note")
            qty_raw = self._cell(row, "qty")

            if normalize.is_group_row(name) or normalize.is_group_row(code):
                self.group_rows.append(r)
                continue

            # 位置号列留空、却把位号写进了备注列：先记下候选，
            # 由核对器用设计文件里的位号集合过滤后再决定是否采用
            note_refs = normalize.refs_from_note(note) if not normalize.split_refs(refs) else []
            if note_refs:
                self.note_ref_rows.append(r)

            if not (code or name or refs):
                if item or qty_raw:
                    self.incomplete_rows.append(r)
                    self.lines.append(
                        {
                            "row": r, "item": item, "code": "", "name": "", "spec": "",
                            "refs": "", "qty": _number(qty_raw), "qtyRaw": qty_raw,
                            "refList": [], "incomplete": True, "group": False,
                            "note": note, "noteRefs": note_refs, "refsSource": "位置号",
                        }
                    )
                continue

            self.lines.append(
                {
                    "row": r, "item": item, "code": code, "name": name, "spec": spec,
                    "refs": refs, "qty": _number(qty_raw), "qtyRaw": qty_raw,
                    "refList": normalize.split_refs(refs), "incomplete": False, "group": False,
                    "note": note, "noteRefs": note_refs, "refsSource": "位置号",
                }
            )

    # -- 统计 ---------------------------------------------------------------
    @property
    def real_lines(self) -> list[dict[str, Any]]:
        return [l for l in self.lines if not l["incomplete"]]

    def all_refs(self) -> set[str]:
        """所有位号的集合。

        注意：集合会丢掉「一个位号出现了几次」的信息，只适合判断
        「设计文件里的位号有没有出现在 BOM 里」。要检查跨行重复分配，
        请用 ref_occurrences()。
        """
        out: set[str] = set()
        for line in self.lines:
            out.update(line["refList"])
        return out

    def ref_occurrences(self) -> dict[str, list[int]]:
        """位号 → 出现的行号列表（同一行重复会出现相同行号）。

        与 all_refs() 不同，这里保留每一次出现：长度为 1 表示只被
        一行认领，长度 > 1 表示跨行（或同行）重复分配。
        """
        out: dict[str, list[int]] = {}
        for line in self.lines:
            for ref in line["refList"]:
                out.setdefault(ref, []).append(line["row"])
        return out

    def detail_rows(self) -> list[dict[str, Any]]:
        return self.lines

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "columns": self.columns,
            "headerRow": self.header_row,
            "header": self.header,
            "detailRows": len(self.real_lines),
            "incompleteRows": len(self.incomplete_rows),
            "groupRows": len(self.group_rows),
            "refCount": len(self.all_refs()),
            "maxRow": len(self.rows),
        }


def _number(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def load_bom(path: str, sheet: int | str | None = None) -> BomFile:
    rows, _ = load_rows(path, sheet)
    if not rows:
        raise ValueError("BOM 文件为空")
    hdr_idx = find_header_row(rows, HEADER_KEYS)
    header = [text_of(v) for v in rows[hdr_idx - 1]] if hdr_idx <= len(rows) else []

    columns = {
        "item": match_column(header, "项次", "序号", "行号") or FALLBACK["item"],
        "code": match_column(header, "子项物料编码", "物料编码", "物料编号") or FALLBACK["code"],
        "name": match_column(header, "子项物料名称", "物料名称", "名称") or FALLBACK["name"],
        "spec": match_column(header, "子项规格型号", "规格型号", "规格") or FALLBACK["spec"],
        "qty": match_column(header, "用量:分子", "用量", "数量") or FALLBACK["qty"],
        "refs": match_column(header, "位置号", "位号", "位置") or FALLBACK["refs"],
        "note": match_column(header, "备注", "说明") or FALLBACK["note"],
    }
    return BomFile(rows, columns, header, hdr_idx, path)
