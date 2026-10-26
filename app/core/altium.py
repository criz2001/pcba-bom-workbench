"""Altium 设计文件（.SchDoc / .PcbDoc）解析。

依据 bom-cross-check / altium-bom-generator 两个 Skill 中记录的格式要点：

* 二进制文件是 OLE 复合文档（魔数 ``D0CF11E0A1B11AE1``）。
* ``SchDoc`` 的关键流是 ``FileHeader``；
  ``PcbDoc`` 的关键流是 ``Components6/Data``（``Pads6/Data`` 是纯二进制记录，不做解析）。
* 文本类流是「``<uint32 小端长度><正文（含结尾 NUL）>``」的连续记录帧，正文以 ``|`` 开头。
* 子记录的 ``OWNERINDEX`` 指向的父记录下标是 **OWNERINDEX + 1**。
"""

from __future__ import annotations

import struct
from typing import Any

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")

# 原理图记录类型
REC_COMPONENT = "1"
REC_PIN = "2"
REC_DESIGNATOR = "34"
REC_PARAMETER = "41"
REC_MODEL_MOUNT = "44"
REC_MODEL_DETAIL = "45"


class AltiumParseError(RuntimeError):
    """设计文件无法解析时抛出。"""


def is_ole(data: bytes) -> bool:
    return data[:8] == OLE_MAGIC


def _decode_record(raw: bytes) -> str:
    """记录正文解码。

    Altium 记录绝大多数是 UTF-8，但 ``PcbDoc`` 的描述字段等常被按本地代码页
    （中文 Windows 是 GBK）写进去。先按 UTF-8 解，出现无效字节就改用 GBK，
    否则中文会变成一串 ``\\ufffd``。
    """
    text = raw.decode("utf-8", "replace")
    if "\ufffd" not in text:
        return text
    try:
        return raw.decode("gbk")
    except UnicodeDecodeError:
        return text


def parse_records(data: bytes) -> list[str]:
    """解析 ``<u32 len><payload with trailing NUL>`` 记录帧。

    长度异常时向前重新同步，尽量不因单个坏记录丢掉整份文件。
    """
    recs: list[str] = []
    i, n = 0, len(data)
    while i < n - 4:
        ln = struct.unpack_from("<I", data, i)[0]
        if ln == 0 or ln > n - i:
            j = data.find(b"|", i + 1)
            if j < 0:
                break
            i = j
            continue
        body = data[i + 4:i + 4 + ln]
        i += 4 + ln
        body = body.rstrip(b"\x00")
        if not body.startswith(b"|"):
            continue
        recs.append(_decode_record(body))
    return recs


def parse_ascii_records(text: str) -> list[str]:
    """兼容以 ASCII 形式保存的 Altium 文件（每条记录以 ``|`` 开头、以换行分隔）。"""
    recs = [line.strip() for line in text.splitlines() if line.startswith("|")]
    return recs


def kv(rec: str) -> dict[str, str]:
    """记录字段解析，键统一转小写。

    ⚠️ 真实 Altium 文件用的是 PascalCase（``LibReference``、``Text``、``OwnerIndex``），
    而自己拼的 ASCII 样例是全大写（``LIBREFERENCE`` / ``TEXT`` / ``OWNERINDEX``）。
    按固定大小写取值会让真实文件「一个字段都取不到」——位号、规格、封装全为空，
    而且因为 OWNERINDEX 解析失败，子记录挂不到父元件上，整份原理图等于没解析。
    统一小写后两种写法都能取到。
    """
    out: dict[str, str] = {}
    for part in rec.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v
    return out


def _open_stream(data: bytes, *names: str) -> bytes | None:
    try:
        import olefile
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确提示
        raise AltiumParseError("缺少 olefile 依赖，无法解析 Altium 二进制文件") from exc

    import io

    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        for name in names:
            path = name.split("/")
            if ole.exists(path):
                return ole.openstream(path).read()
    finally:
        ole.close()
    return None


def _records_from(data: bytes, stream_names: tuple[str, ...]) -> list[str]:
    if is_ole(data):
        raw = None
        for name in stream_names:
            raw = _open_stream(data, name)
            if raw is not None:
                break
        if raw is None:
            raise AltiumParseError(
                "OLE 复合文档中未找到关键流：" + " / ".join(stream_names)
            )
        return parse_records(raw)

    # 非 OLE：可能是 ASCII 保存的 Altium 文件
    text = data.decode("utf-8", "replace")
    if "\ufffd" in text:
        try:
            text = data.decode("gbk")
        except UnicodeDecodeError:
            pass
    recs = parse_ascii_records(text)
    if recs:
        return recs
    recs = parse_records(data)
    if recs:
        return recs
    raise AltiumParseError("既不是 OLE 复合文档，也未能解析出文本记录")


def _stream_list(data: bytes) -> list[tuple[str, int]]:
    try:
        import olefile
    except ImportError:  # pragma: no cover
        return []

    import io

    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception:
        return []
    try:
        return [("/".join(s), ole.get_size(s)) for s in sorted(ole.listdir())]
    finally:
        ole.close()


# ---------------------------------------------------------------------------
# 原理图
# ---------------------------------------------------------------------------

def extract_sch(data: bytes, filename: str = "") -> dict[str, Any]:
    """从 .SchDoc 提取元件（位号 / 标注值 / 封装 / 引脚数）。"""
    recs = _records_from(data, ("FileHeader",))
    K = [kv(r) for r in recs]
    for idx, d in enumerate(K):
        d["_idx"] = str(idx)

    def resolve_parent(d: dict[str, str], kinds: tuple[str, ...]) -> dict[str, str] | None:
        """解析 OwnerIndex 指向的父记录。

        ⚠️ Altium 的 ``OwnerIndex`` 相对解析列表存在 **+1 偏移**，因此优先试
        ``OwnerIndex + 1``；个别导出方式不加偏移，故在类型不符时回退到原值。
        """
        try:
            oi = int(d.get("ownerindex", ""))
        except (TypeError, ValueError):
            return None
        for idx in (oi + 1, oi):
            if 0 <= idx < len(K) and K[idx].get("record") in kinds:
                return K[idx]
        return None

    comps: list[dict[str, Any]] = []
    for idx, d in enumerate(K):
        if d.get("record") == REC_COMPONENT:
            comps.append(
                {
                    "index": idx,
                    "libref": d.get("libreference", ""),
                    "description": d.get("componentdescription", ""),
                    "designator": "",
                    "comment": "",
                    "value": "",
                    "pins": 0,
                    "params": {},
                    "footprints": [],
                }
            )
    by_idx = {c["index"]: c for c in comps}

    for d in K:
        kind = d.get("record")
        if kind == REC_DESIGNATOR:
            parent = resolve_parent(d, (REC_COMPONENT,))
            if parent is not None and d.get("name", "").lower() == "designator":
                by_idx[int(parent["_idx"])]["designator"] = d.get("text", "").strip()
        elif kind == REC_PIN:
            parent = resolve_parent(d, (REC_COMPONENT,))
            if parent is not None:
                by_idx[int(parent["_idx"])]["pins"] += 1
        elif kind == REC_PARAMETER:
            parent = resolve_parent(d, (REC_COMPONENT,))
            if parent is not None:
                idx = int(parent["_idx"])
                name = d.get("name", "")
                text = d.get("text", "")
                by_idx[idx]["params"][name] = text
                low = name.lower()
                if low == "comment":
                    by_idx[idx]["comment"] = text
                elif low == "value":
                    by_idx[idx]["value"] = text
        elif kind == REC_MODEL_DETAIL:
            target = None
            parent = resolve_parent(d, (REC_COMPONENT, REC_MODEL_MOUNT))
            if parent is not None and parent.get("record") == REC_MODEL_MOUNT:
                grand = resolve_parent(parent, (REC_COMPONENT,))
                if grand is not None:
                    target = by_idx.get(int(grand["_idx"]))
            elif parent is not None:
                target = by_idx.get(int(parent["_idx"]))
            if target is not None and (d.get("modeltype", "").upper() == "PCBLIB"):
                name = d.get("modelname", "")
                if name and name not in target["footprints"]:
                    target["footprints"].append(name)

    for c in comps:
        c["footprint"] = ",".join(c["footprints"])
        # 规格取值优先级：Value > Comment > 描述
        c["spec"] = c["value"] or c["comment"] or c["description"] or c["libref"]

    return {
        "kind": "schematic",
        "filename": filename,
        "record_count": len(K),
        "components": comps,
        "designators": sorted_lnk(c["designator"] for c in comps if c["designator"]),
        "streams": _stream_list(data),
    }


# ---------------------------------------------------------------------------
# PCB
# ---------------------------------------------------------------------------

def extract_pcb(data: bytes, filename: str = "") -> dict[str, Any]:
    """从 .PcbDoc 提取元件（位号 / 实际封装 PATTERN / 高度 / 层）。"""
    recs = _records_from(data, ("Components6/Data", "Components/Data"))
    comps: list[dict[str, Any]] = []
    for rec in recs:
        d = kv(rec)
        des = d.get("sourcedesignator", "") or d.get("designator", "")
        pattern = d.get("pattern", "") or d.get("sourcelibreference", "")
        comps.append(
            {
                "designator": des.strip(),
                "pattern": pattern.strip(),
                "height": d.get("height", ""),
                "layer": d.get("layer", ""),
                "libref": d.get("sourcelibreference", ""),
                "footprintlib": d.get("sourcefootprintlibrary", ""),
                "description": d.get("sourcedescription", ""),
            }
        )

    return {
        "kind": "pcb",
        "filename": filename,
        "component_count": len(comps),
        "components": comps,
        "designators": sorted_lnk(c["designator"] for c in comps if c["designator"]),
        "unlabeled": [c for c in comps if not c["designator"]],
        "streams": _stream_list(data),
    }


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def ref_sort_key(ref: str) -> tuple[str, int, str]:
    """位号自然排序：按字母前缀 + 数字。"""
    import re

    s = (ref or "").strip()
    m = re.match(r"^([A-Za-z_]*)(\d*)", s)
    prefix = (m.group(1) or s).upper() if m else s.upper()
    num = int(m.group(2)) if m and m.group(2) else 0
    return prefix, num, s.upper()


def sorted_lnk(refs) -> list[str]:
    return sorted({r for r in refs if r}, key=ref_sort_key)


def parse_ref_list(text: str) -> list[str]:
    """拆分位置号文本（支持半角/全角逗号、分号、顿号、空白）。"""
    import re

    return [r for r in re.split(r"[,，;、\s]+", str(text or "")) if r.strip()]


def natural_key(ref: str) -> tuple[str, int, str]:
    return ref_sort_key(ref)
