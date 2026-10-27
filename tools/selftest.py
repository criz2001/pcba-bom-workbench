"""端到端自检：构造样例设计文件与表格，跑完「核对 + 生成」全流程。

    python tools/selftest.py

样例覆盖 10 类核对规则与主要生成分支，用来验证引擎与接口是否可用。
运行在临时工作区，不影响真实 workspace。
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = os.environ.get("BOM_SELFTEST_DIR") or tempfile.mkdtemp(prefix="bom-selftest-")
# 默认在临时工作区运行；如需写进真实 workspace，可先设置环境变量 BOM_WORKSPACE
os.environ.setdefault("BOM_WORKSPACE", os.path.join(TMP, "workspace"))

from app.server import create_app  # noqa: E402

# ---------------------------------------------------------------------------
# 样例设计文件（ASCII 形式的 Altium 记录，解析器同样支持）
# ---------------------------------------------------------------------------

SCHEDOC = """|RECORD=31|Description=Demo Sheet
|RECORD=1|LIBREFERENCE=RES|COMPONENTDESCRIPTION=Resistor
|RECORD=34|OWNERINDEX=0|NAME=Designator|TEXT=R1
|RECORD=41|OWNERINDEX=0|NAME=Comment|TEXT=1K
|RECORD=41|OWNERINDEX=0|NAME=Value|TEXT=1K
|RECORD=45|OWNERINDEX=0|MODELTYPE=PCBLIB|MODELNAME=0603
|RECORD=2|OWNERINDEX=0|DESIGNATOR=1
|RECORD=2|OWNERINDEX=0|DESIGNATOR=2
|RECORD=1|LIBREFERENCE=CAP|COMPONENTDESCRIPTION=Capacitor
|RECORD=34|OWNERINDEX=7|NAME=Designator|TEXT=C1
|RECORD=41|OWNERINDEX=7|NAME=Comment|TEXT=104
|RECORD=41|OWNERINDEX=7|NAME=Value|TEXT=104
|RECORD=45|OWNERINDEX=7|MODELTYPE=PCBLIB|MODELNAME=0603
|RECORD=2|OWNERINDEX=7|DESIGNATOR=1
|RECORD=2|OWNERINDEX=7|DESIGNATOR=2
|RECORD=1|LIBREFERENCE=HT1621|COMPONENTDESCRIPTION=LCD Driver
|RECORD=34|OWNERINDEX=14|NAME=Designator|TEXT=U1
|RECORD=41|OWNERINDEX=14|NAME=Comment|TEXT=HT1621
|RECORD=41|OWNERINDEX=14|NAME=Value|TEXT=HT1621B
|RECORD=45|OWNERINDEX=14|MODELTYPE=PCBLIB|MODELNAME=SSOP48
|RECORD=2|OWNERINDEX=14|DESIGNATOR=1
|RECORD=2|OWNERINDEX=14|DESIGNATOR=48
|RECORD=1|LIBREFERENCE=CONN-5P|COMPONENTDESCRIPTION=Connector
|RECORD=34|OWNERINDEX=21|NAME=Designator|TEXT=J1
|RECORD=41|OWNERINDEX=21|NAME=Comment|TEXT=1.25-5P
|RECORD=41|OWNERINDEX=21|NAME=Value|TEXT=1.25-5P
|RECORD=45|OWNERINDEX=21|MODELTYPE=PCBLIB|MODELNAME=1.25-5P
|RECORD=2|OWNERINDEX=21|DESIGNATOR=1
|RECORD=2|OWNERINDEX=21|DESIGNATOR=5
|RECORD=1|LIBREFERENCE=SS34|COMPONENTDESCRIPTION=Schottky Diode
|RECORD=34|OWNERINDEX=28|NAME=Designator|TEXT=D1
|RECORD=41|OWNERINDEX=28|NAME=Comment|TEXT=SS34
|RECORD=41|OWNERINDEX=28|NAME=Value|TEXT=SS34
|RECORD=45|OWNERINDEX=28|MODELTYPE=PCBLIB|MODELNAME=SMA
"""

PCBDOC = """|SOURCEDESIGNATOR=R1|PATTERN=0603|HEIGHT=68.8976|LAYER=TOP|SOURCELIBREFERENCE=RES
|SOURCEDESIGNATOR=C1|PATTERN=0603|HEIGHT=68.8976|LAYER=TOP|SOURCELIBREFERENCE=CAP
|SOURCEDESIGNATOR=U1|PATTERN=SSOP48|HEIGHT=169.2913|LAYER=TOP|SOURCELIBREFERENCE=HT1621
|SOURCEDESIGNATOR=J1|PATTERN=1.25-5P|HEIGHT=100|LAYER=TOP|SOURCELIBREFERENCE=CONN-5P
|SOURCEDESIGNATOR=D1|PATTERN=SMA|HEIGHT=90|LAYER=TOP|SOURCELIBREFERENCE=SS34
|PATTERN=LED-2P|HEIGHT=50|LAYER=BOTTOM|SOURCELIBREFERENCE=BACKLIGHT
"""

MASTER_ROWS = [
    ["物料编码", "物料名称", "规格型号", "物料属性", "数据状态", "禁用状态", "物料属性2", "基本单位"],
    ["1.01.03.102", "贴片电阻 1K 1% 0603", "0603 1K 1% 100mW", "", "正常", "否", "", "PCS"],
    ["1.02.03.002", "贴片电容 0.1uF 50V X7R 0603", "0603 0.1uF X7R 50V", "", "正常", "否", "", "PCS"],
    ["1.07.01.006", "HT1621B LCD 驱动", "SSOP48 原厂", "", "正常", "否", "", "PCS"],
    ["1.05.01.033", "5 脚连接器 1.25mm", "1.25-5P 卧贴", "", "正常", "否", "", "PCS"],
    ["1.03.02.051", "肖特基二极管 SS34", "SMA 40V 3A", "", "正常", "否", "", "PCS"],
    ["1.04.05.110", "ESP32-C2 模组", "模组 2MB", "", "正常", "是", "", "PCS"],
]

BOM_ROWS = [
    ["项次", "父项物料编码", "子项物料编码", "子项物料名称", "子项规格型号", "用量:分子", "用量:分母", "位置号", "备注"],
    [1, "", "1.01.03.102", "贴片电阻 1K 1% 0603", "0603 1K 1% 100mW", 1, 1, "R1", ""],
    [2, "", "1.02.03.002", "贴片电容 0.1uF 50V X7R 0805", "0805 0.1uF X7R 50V", 2, 1, "C1", ""],
    [3, "", "", "HT1621B LCD 驱动", "SSOP48", 1, 1, "U1", ""],
    [4, "", "1.99.99.999", "5 脚连接器 1.25mm", "1.25-5P 卧贴", 1, 1, "J5", ""],
    [6, "", "1.03.02.051", "肖特基二极管 SS34", "SMA 40V 3A", 2, 1, "D1，D2", ""],
    [7, "", "", "", "", 3, 1, "", ""],
    # R1 在第 1 行已经分配过，这一行用于验证「位号重复」规则
    [8, "", "1.01.03.102", "贴片电阻 1K 1% 0603", "0603 1K 1% 100mW", 1, 1, "R1", ""],
]

TEMPLATE_ROWS = [
    ["项次", "子项物料编码", "子项物料名称", "子项规格型号", "子项单位", "用量:分子", "用量:分母", "位置号", "备注"],
]


def write_xlsx(path: str, rows: list[list]) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)


def write_bad_dimension_xlsx(path: str, rows: list[list]) -> None:
    """写出一个 <dimension ref="A1"/> 标记错误的表格（模拟部分 ERP 导出）。"""
    import re
    import zipfile

    write_xlsx(path, rows)
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = data.decode("utf-8")
                text = re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1"/>', text)
                data = text.encode("utf-8")
            dst.writestr(item, data)
    os.replace(tmp, path)


def build_fixtures() -> dict[str, str]:
    files = {}
    for name, content in (("demo.SchDoc", SCHEDOC), ("demo.PcbDoc", PCBDOC)):
        path = os.path.join(TMP, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        files[name] = path

    for name, rows in (("master.xlsx", MASTER_ROWS), ("bom.xlsx", BOM_ROWS),
                       ("template.xlsx", TEMPLATE_ROWS)):
        path = os.path.join(TMP, name)
        write_xlsx(path, rows)
        files[name] = path
    return files


# ---------------------------------------------------------------------------
def upload(client, kind: str, path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    resp = client.post(
        "/api/upload",
        data={"kind": kind, "file": (io.BytesIO(data), os.path.basename(path))},
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"], f"上传 {kind} 失败：{body}"
    return body["upload"]


def wait_task(client, task_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}").get_json()["task"]
        if task["status"] != "running":
            return task
        time.sleep(0.2)
    raise AssertionError("任务超时未完成")


def main() -> int:
    files = build_fixtures()
    app = create_app()
    client = app.test_client()
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(("  [OK]   " if condition else "  [FAIL] ") + label + (f" — {detail}" if detail else ""))
        if not condition:
            failures.append(label)

    print("\n== 1. 上传与解析 ==")
    sch = upload(client, "schematic", files["demo.SchDoc"])
    pcb = upload(client, "pcb", files["demo.PcbDoc"])
    bom = upload(client, "bom", files["bom.xlsx"])
    master = upload(client, "master", files["master.xlsx"])
    template = upload(client, "template", files["template.xlsx"])

    check("原理图解析出 5 个元件", sch["summary"]["components"] == 5, str(sch["summary"]))
    check("PCB 解析出 6 个元件", pcb["summary"]["components"] == 6, str(pcb["summary"]))
    check("PCB 有 1 个无位号元件", pcb["summary"]["unlabeled"] == 1)
    check("BOM 明细行 6 行", bom["summary"]["detailRows"] == 6, str(bom["summary"]))
    check("BOM 残缺空行 1 行", bom["summary"]["incompleteRows"] == 1)
    check("物料总表 6 条", master["summary"]["count"] == 6, str(master["summary"]))

    # 回归：ERP 导出可能把 <dimension> 写成 A1，实际却有上万行；
    # 只读模式不能因此只读到第一格。
    bad_dim = os.path.join(TMP, "master-bad-dimension.xlsx")
    write_bad_dimension_xlsx(bad_dim, MASTER_ROWS)
    from app.core import master as master_mod

    m_bad = master_mod.load_master(bad_dim)
    check("维度标记错误的总表仍能解析全部行",
          m_bad.count == len(MASTER_ROWS) - 1, str(m_bad.summary()))
    check("维度标记错误时仍能定位编码列", m_bad.columns.get("code") == 1, str(m_bad.columns))

    print("\n== 2. 基准一致性 ==")
    base = client.post("/api/baseline", json={}).get_json()
    check("基准不一致（PCB 多 1 个无位号元件不影响位号集合）", base["identical"] is True, str(base))

    print("\n== 3. 三方交叉核对 ==")
    resp = client.post("/api/check/run", json={}).get_json()
    task = wait_task(client, resp["taskId"])
    check("核对任务成功", task["status"] == "done", task.get("error", ""))
    result = task["result"]
    kinds = {p["kind"] for p in result["problems"]}
    for expected in ["封装不符", "名称与总表不符", "位号缺失", "位号不存在",
                     "位号重复", "用量≠位号数", "缺物料编码", "编码不存在",
                     "位号格式", "项次跳号", "空行(未填写)"]:
        check(f"命中规则「{expected}」", expected in kinds, f"实际：{sorted(kinds)}")
    dup = [p for p in result["problems"] if p["kind"] == "位号重复"]
    check("重复位号定位到后出现的行",
          len(dup) == 1 and dup[0]["row"] == 8, str(dup))

    # 备注列位号：位置号整列为空时从备注回填；备注中设计文件不存在的位号
    # 不能被静默丢掉，否则会误报「用量≠位号数」。
    note_bom_path = os.path.join(TMP, "bom-note-refs.xlsx")
    write_xlsx(note_bom_path, [
        BOM_ROWS[0],
        [1, "", "1.01.03.102", "贴片电阻 1K 1% 0603", "0603 1K 1% 100mW", 3, 1, "", "R1 C1 Z9"],
    ])
    from app.core import altium as altium_mod
    from app.core import bom_reader as bom_reader_mod
    from app.core import checker as checker_mod

    sch_info = altium_mod.extract_sch(open(files["demo.SchDoc"], "rb").read(), "demo.SchDoc")
    pcb_info = altium_mod.extract_pcb(open(files["demo.PcbDoc"], "rb").read(), "demo.PcbDoc")
    note_bom = bom_reader_mod.load_bom(note_bom_path)
    note_res = checker_mod.run_check(sch_info, pcb_info, note_bom, None)
    row2 = [p for p in note_res.problems if p["row"] == 2]
    check("备注位号回填后不再误报用量",
          not any(p["kind"] == "用量≠位号数" for p in row2), str(row2))
    check("备注中设计文件不存在的位号会被报出",
          any(p["kind"] == "位号不存在" and "Z9" in p["msg"] for p in row2), str(row2))
    check("输出文件已生成", bool(task["output"]), str(task.get("output")))
    check("值比对有结果", result["metrics"]["valueDiff"] >= 1, str(result["metrics"]))
    check("问题分级统计自洽",
          result["metrics"]["severe"] + result["metrics"]["normal"] + result["metrics"]["info"]
          == result["metrics"]["total"])

    print("\n== 4. 导出结果 Excel ==")
    dl = client.get(f"/api/tasks/{task['id']}/download")
    check("下载返回 xlsx", dl.status_code == 200 and len(dl.data) > 3000,
          f"{dl.status_code} / {len(dl.data)} bytes")
    if dl.status_code == 200:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(dl.data))
        check("结果含 4 个 Sheet", len(wb.sheetnames) == 4, str(wb.sheetnames))
        ws = wb.worksheets[0]
        check("原表新增「核对结果」列",
              any(c.value == "核对结果（自动核对）" for c in ws[1]))
        wb.close()

    print("\n== 5. BOM 生成 ==")
    resp = client.post("/api/generate/preview", json={}).get_json()
    check("生成预览可用", resp["ok"] and resp["componentCount"] >= 5, str(resp.get("counts")))
    resp = client.post("/api/generate/run", json={"mode": "merge"}).get_json()
    gen = wait_task(client, resp["taskId"])
    check("生成任务成功", gen["status"] == "done", gen.get("error", ""))
    stats = gen["result"]["stats"]
    check("合并行数 ≤ 元件数", stats["rowCount"] <= stats["componentCount"],
          f"{stats['rowCount']} / {stats['componentCount']}")
    check("存在待确认项（PCB 无位号元件）", stats["pending"] >= 1, str(stats))
    check("检测到 PCB 无位号元件", len(stats["unlabeledPcb"]) == 1, str(stats["unlabeledPcb"]))
    check("每行用量 = 该行位号数",
          all(len(r["refs"].split()) == r["qty"] for r in gen["result"]["rows"]))
    check("模板列数被识别", gen["result"]["meta"]["template"]["columnCount"] == 9,
          str(gen["result"]["meta"]["template"]["columnCount"]))

    gdl = client.get(f"/api/tasks/{gen['id']}/download")
    check("生成文件可下载", gdl.status_code == 200 and len(gdl.data) > 3000,
          f"{gdl.status_code} / {len(gdl.data)} bytes")

    print("\n== 6. 物料库接口 ==")
    mats = client.get("/api/library/materials?page=1&pageSize=5").get_json()
    check("物料库分页可用", mats["ok"] and mats["total"] == 6, str(mats.get("total")))
    check("物料库状态筛选可用",
          client.get("/api/library/materials?status=disabled").get_json()["total"] == 1)
    check("模板列表可用", len(client.get("/api/library/templates").get_json()["templates"]) == 1)

    print("\n== 7. 页面渲染 ==")
    for route in ["/", "/check/setup", "/check/running", "/check/result", "/check/detail",
                  "/gen/setup", "/gen/result", "/library"]:
        r = client.get(route)
        check(f"{route} 返回 200", r.status_code == 200 and b"app-window" in r.data,
              str(r.status_code))

    print("\n== 8. 工作区状态持久化 ==")
    state = client.get("/api/state").get_json()
    check("状态含任务记录", len(state["tasks"]) >= 2, str(len(state["tasks"])))
    check("状态含上次核对", bool(state["lastCheck"]))
    check("状态含上次生成", bool(state["lastGenerate"]))
    check("状态含物料总表", state["material"] and state["material"]["count"] == 6)

    print("\n== 9. 桌面窗口桥接（pywebview 原生能力） ==")
    from app import desktop

    store = app.extensions["store"]
    dd = os.path.join(TMP, "desktop-out")
    os.makedirs(dd, exist_ok=True)

    class FakeWindow:
        """替身窗口：模拟原生「另存为」对话框的返回值。"""

        def __init__(self, answer):
            self.answer = answer

        def create_file_dialog(self, *args, **kwargs):
            return (self.answer,) if self.answer else None

    api = desktop.DesktopApi(store)
    port = desktop.free_port()
    check("可用端口探测正常", isinstance(port, int) and 0 < port < 65536, str(port))
    check("桌面模式标识正确", api.app_info()["mode"] == "desktop")
    check("输出目录可访问", os.path.isdir(api.app_info()["outputs"]))

    target = os.path.join(dd, "核对结果.xlsx")
    api.bind_window(FakeWindow(target))
    saved = api.save_task_output(task["id"])
    check("结果另存为成功", saved.get("ok") is True and os.path.exists(target), str(saved))
    check("另存文件与服务器结果一致",
          os.path.getsize(target) == os.path.getsize(task["output"]["path"]))

    api.bind_window(FakeWindow(None))
    cancelled = api.save_task_output(task["id"])
    check("取消保存被正确识别", cancelled.get("ok") is False and cancelled.get("cancelled") is True,
          str(cancelled))

    csv_path = os.path.join(dd, "待确认清单.csv")
    api.bind_window(FakeWindow(csv_path))
    text_res = api.save_text("待确认清单.csv", "位号,说明\r\nU3,test")
    check("文本导出成功", text_res.get("ok") is True and os.path.exists(csv_path), str(text_res))

    missing = api.save_task_output("not-a-task")
    check("无效任务号返回错误", missing.get("ok") is False, str(missing))

    assets = os.path.join(ROOT, "app", "static", "assets")
    api_js = open(os.path.join(assets, "api.js"), encoding="utf-8").read()
    app_js = open(os.path.join(assets, "app.js"), encoding="utf-8").read()
    check("前端已接入桌面保存与目录打开",
          "save_task_output" in api_js and "saveTaskOutput" in api_js
          and "openFolder" in api_js and "data-desktop-only" in app_js)

    print("\n== 10. 浏览器回退路径（pywebview 缺失时） ==")
    fb_app = create_app()
    fb_store = fb_app.extensions["store"]
    fb_port = desktop.free_port(8910)
    desktop.start_browser_server(fb_app, fb_port)
    ok = False
    for _ in range(50):
        try:
            import urllib.request

            with urllib.request.urlopen(f"http://127.0.0.1:{fb_port}/api/status", timeout=2) as resp:
                ok = resp.status == 200
            break
        except Exception:
            time.sleep(0.1)
    check("回退路径可独立起服务", ok, f"port={fb_port}")
    check("回退路径与窗口模式互不占用端口",
          fb_port != port, f"fallback={fb_port} window={port}")
    check("回退路径工作区可用", os.path.isdir(fb_store.root))

    print("\n== 11. 单实例保护 ==")
    if sys.platform == "win32":
        lock_dir = os.path.join(TMP, "lock-test")
        check("首次启动可获取实例锁", desktop.acquire_single_instance(lock_dir) is True)
        check("重复启动被拦截（不会开出第二个窗口）",
              desktop.acquire_single_instance(lock_dir) is False)
        check("找不到已有窗口时不会误报切换成功",
              desktop.focus_existing_window("__definitely_not_a_window__") is False)
    else:
        check("非 Windows 平台跳过实例锁检查", True)

    print("\n== 12. 工作区位置解析（安装版数据目录） ==")
    from app import server as server_mod

    cfg_dir = os.path.join(TMP, "cfg")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_ws = os.path.join(TMP, "cfg-workspace")
    with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8-sig") as fh:
        # 故意写成带 BOM 的 UTF-8：PowerShell 的默认写法就是带 BOM
        fh.write(json.dumps({"workspace": cfg_ws}, ensure_ascii=False))

    env_backup = os.environ.pop("BOM_WORKSPACE", None)
    project_backup = server_mod.PROJECT_DIR
    try:
        server_mod.PROJECT_DIR = cfg_dir
        check("config.json 指定的工作区被采用",
              server_mod.resolve_workspace() == os.path.abspath(cfg_ws),
              server_mod.resolve_workspace())
        os.remove(os.path.join(cfg_dir, "config.json"))
        check("没有 config.json 时回落到项目内 workspace",
              server_mod.resolve_workspace() == os.path.join(cfg_dir, "workspace"),
              server_mod.resolve_workspace())
    finally:
        server_mod.PROJECT_DIR = project_backup
        if env_backup is not None:
            os.environ["BOM_WORKSPACE"] = env_backup

    print("\n== 13. 匹配不上物料总表时仍然输出 BOM ==")
    # 关键回归：没有物料总表时，生成准备页不能报错，BOM 也必须照常输出并标注
    store.master = None
    store.selection["master"] = None

    pv2 = client.post("/api/generate/preview", json={}).get_json()
    check("无物料总表时生成准备页不再报错", pv2.get("ok") is True, str(pv2.get("error", "")))
    check("预览把全部元件标为待确认",
          pv2.get("counts", {}).get("pending") == pv2.get("componentCount"),
          str(pv2.get("counts")))

    run2 = client.post("/api/generate/run", json={"mode": "merge"}).get_json()
    task2 = wait_task(client, run2["taskId"])
    check("无物料总表时仍然生成 BOM", task2["status"] == "done", task2.get("error", ""))
    rows2 = (task2.get("result") or {}).get("rows") or []
    check("未匹配元件全部保留在 BOM 中", len(rows2) > 0, f"{len(rows2)} 行")
    check("未匹配行的名称不留空", all(r["name"] for r in rows2),
          str([r["name"] for r in rows2]))
    check("未匹配行在备注里标注待确认", all("待确认" in r["note"] for r in rows2),
          str([r["note"] for r in rows2]))
    check("统计里给出未匹配行数",
          task2["metrics"].get("unmatchedRows") == len(rows2), str(task2["metrics"]))

    dl2 = client.get(f"/api/tasks/{task2['id']}/download")
    check("未匹配时结果文件可下载", dl2.status_code == 200 and len(dl2.data) > 3000,
          f"{dl2.status_code} / {len(dl2.data)} bytes")
    if dl2.status_code == 200:
        import openpyxl
        from openpyxl.comments import Comment  # noqa: F401

        wb2 = openpyxl.load_workbook(io.BytesIO(dl2.data))
        ws2 = wb2.worksheets[0]
        header = [c.value for c in ws2[1]]
        code_col = header.index("子项物料编码") + 1
        note_col = header.index("备注") + 1
        check("未匹配行的编码列留空（避免被误导入）",
              all(ws2.cell(r, code_col).value in (None, "") for r in range(2, len(rows2) + 2)))
        check("未匹配行的编码列带批注说明",
              all(ws2.cell(r, code_col).comment is not None for r in range(2, len(rows2) + 2)))
        check("未匹配行的编码列有琥珀底色",
              all(ws2.cell(r, code_col).fill.start_color.rgb in ("00FFEB9C", "FFFFEB9C")
                  for r in range(2, len(rows2) + 2)),
              str(ws2.cell(2, code_col).fill.start_color.rgb))
        check("未匹配行的备注列写有标注",
              all("待确认" in str(ws2.cell(r, note_col).value or "") for r in range(2, len(rows2) + 2)))
        wb2.close()

    print("\n== 14. 安装组件与图标 ==")
    icon = os.path.join(ROOT, "app", "static", "assets", "app.ico")
    check("应用图标存在", os.path.exists(icon), icon)
    if os.path.exists(icon):
        with open(icon, "rb") as fh:
            head = fh.read(6)
        frames = int.from_bytes(head[4:6], "little") if len(head) >= 6 else 0
        check("图标是合法的 ICO 且含图像帧",
              head[:4] == b"\x00\x00\x01\x00" and frames >= 1,
              f"{head[:4]!r} frames={frames}")

    for name in ("install.ps1", "安装.bat", "uninstall.ps1", "卸载.bat"):
        check(f"安装组件 {name} 存在", os.path.exists(os.path.join(ROOT, name)))

    installer_path = os.path.join(ROOT, "install.ps1")
    installer = ""
    if os.path.exists(installer_path):
        with open(installer_path, encoding="utf-8-sig") as fh:
            installer = fh.read()
    check("安装器会创建桌面快捷方式",
          "CreateShortcut" in installer and "GetFolderPath('Desktop')" in installer)
    check("安装器会写入卸载注册表项", "CurrentVersion\\Uninstall" in installer)
    check("安装器会生成 install.json", "install.json" in installer)
    check("安装器会检查 Python 并预装运行环境",
          "Find-SystemPython" in installer and "Test-Venv" in installer and "-SkipEnvSetup" in installer)

    helper_path = os.path.join(ROOT, "app", "startup_error.ps1")
    check("启动失败提示脚本存在", os.path.exists(helper_path), helper_path)
    launcher = ""
    start_bat = os.path.join(ROOT, "start.bat")
    if os.path.exists(start_bat):
        with open(start_bat, encoding="utf-8", errors="replace") as fh:
            launcher = fh.read()
    check("启动器会写 start.log 并调用错误提示",
          "start.log" in launcher and "startup_error.ps1" in launcher)

    print("\n" + "=" * 62)
    if failures:
        print(f"自检失败 {len(failures)} 项：")
        for f in failures:
            print("  - " + f)
        print(f"临时目录：{TMP}")
        return 1
    print("自检全部通过 ✅")
    print(f"临时目录：{TMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
