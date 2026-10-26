"""规格归一化与封装代号提取。

只为「匹配」和「比对」创建归一化值，BOM 与界面始终保留原始文本。
"""

from __future__ import annotations

import re

# 常见贴片封装代号（英制）
CHIP_FOOTPRINTS = (
    "0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512", "3528",
)

# 常见封装类型关键字（用于从名称/规格里识别封装）
PACKAGE_KEYWORDS = (
    "SSOP48", "SSOP", "SOP", "SOT-23", "SOT23", "SOT-223", "SOT89", "SOD-123",
    "SMA", "SMB", "SMC", "DFN", "QFN", "LQFP", "TSSOP", "TO-92", "TO-220",
    "LED-2P", "LED", "PLUG", "USB", "BAT",
)

_CHIP_RE = re.compile(r"(?<!\d)(" + "|".join(CHIP_FOOTPRINTS) + r")(?!\d)", re.I)
_PKG_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in PACKAGE_KEYWORDS) + r")(?![A-Za-z0-9])",
    re.I,
)
_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)$")


def extract_footprint(*texts: str) -> str:
    """从名称 / 规格 / 封装名中提取封装代号（优先贴片代号，其次封装类型）。"""
    for text in texts:
        m = _CHIP_RE.search(str(text or ""))
        if m:
            return m.group(1).upper()
    for text in texts:
        m = _PKG_RE.search(str(text or ""))
        if m:
            return m.group(1).upper()
    return ""


def normalize_value(value: str) -> str:
    """把 104 / 0.1uF / 10u / 5K1 / 100 / 100R 这类写法归一化后比较。"""
    s = str(value or "").strip().upper().replace(" ", "")
    if not s:
        return ""
    # 电容/电阻三位数标法
    if s in ("104", "0.1U", "0.1UF", "100NF"):
        return "0.1UF"
    if s in ("10U", "10UF", "106", "10000000PF"):
        return "10UF"
    if s in ("100UF", "107"):
        return "100UF"
    if s in ("22UF", "226"):
        return "22UF"
    if s in ("1U", "1UF", "105"):
        return "1UF"
    if s in ("4.7UF", "475"):
        return "4.7UF"
    # 5K1 / 4R7 这类 R/K 夹心写法
    m = re.match(r"^(\d+)R(\d+)$", s)
    if m:
        return f"{m.group(1)}.{m.group(2)}R"
    m = re.match(r"^(\d+)K(\d+)$", s)
    if m:
        return f"{m.group(1)}.{m.group(2)}K"
    m = re.match(r"^(\d+)M(\d+)$", s)
    if m:
        return f"{m.group(1)}.{m.group(2)}M"
    # 纯数字在电阻语境中通常表示 Ω
    if _NUM_RE.match(s):
        return s + "R"
    return s


def is_value_like(value: str) -> bool:
    """判断一个字符串是否像「阻值/容值/感值」这类可归一化的参数值。"""
    s = str(value or "").strip().upper().replace(" ", "")
    if not s:
        return False
    if re.fullmatch(r"\d{3}", s):
        return True
    if re.fullmatch(r"\d+(\.\d+)?(R|K|M|U|UF|NF|PF|MH|NH|OHM|Ω)", s):
        return True
    if re.fullmatch(r"\d+[RKM]\d+", s):
        return True
    return False


def values_equivalent(a: str, b: str) -> bool:
    na, nb = normalize_value(a), normalize_value(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # 600R 与 600R@100MHZ 这类带测试条件的写法视为等价。
    # 注意：不能把单位抹掉再比（那会让 1K 与 1M、1R 全部相等）。
    return _strip_qualifier(na) == _strip_qualifier(nb)


def _strip_qualifier(value: str) -> str:
    return value.split("@")[0].strip()


# 三位数标法与直写容值的常见对应，用于在「只有名称」的 ERP 数据里查找
_VALUE_ALIASES = {
    "0.1UF": ("104", "100NF", "0.1U"),
    "10UF": ("106",),
    "100UF": ("107",),
    "22UF": ("226",),
    "1UF": ("105",),
    "4.7UF": ("475",),
}


def value_aliases(value: str) -> set[str]:
    """返回该规格值在文本里可能出现的所有写法（归一化值 + 常见别名）。

    ERP 导出的物料总表经常「规格型号列为空、规格只写在名称里」，
    例如 ``直插电阻1/16W-120K±5％-P``、``贴片电容0603-104-50V``，
    因此需要拿多种写法去名称里找。
    """
    raw = str(value or "").strip().upper().replace(" ", "")
    if not raw:
        return set()
    out = {raw}
    norm = normalize_value(raw)
    if norm:
        out.add(norm)
        out.update(_VALUE_ALIASES.get(norm, ()))
    return {x for x in out if x}


def _strip_qualifier(value: str) -> str:
    return value.split("@")[0].strip()


def split_refs(text: str) -> list[str]:
    return [r.strip() for r in re.split(r"[,，;、\s]+", str(text or "")) if r.strip()]


# 位号形态：1~4 个字母 + 1~4 位数字，可带一个尾字母（R1、C10、LED1、D1A、V42）
_REF_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,4}\d{1,4}[A-Za-z]?)(?![A-Za-z0-9])")


def refs_from_note(note: str) -> list[str]:
    """从备注里提取位号。

    有人填 BOM 时会把位置号写进备注列（位置号列留空）。这里只按「字母+数字」
    的位号形态抽取，避免把「已确认」「2024-01-01」这类文字当成位号；
    调用方还会再用设计文件里的位号集合过滤一次，进一步压掉误判。
    """
    out: list[str] = []
    for m in _REF_TOKEN_RE.finditer(str(note or "")):
        token = m.group(1).upper()
        if token not in out:
            out.append(token)
    return out


def has_bad_separator(text: str) -> bool:
    return bool(re.search(r"[，；、;]", str(text or "")))


def has_empty_ref(text: str) -> bool:
    return ",," in str(text or "").replace("，", ",")


def is_group_row(value: str) -> bool:
    """父级 / 半成品行：形如 ``4-xxx贴片`` ``3-xxx``。"""
    return bool(re.match(r"^\d+-", str(value or "").strip()))
