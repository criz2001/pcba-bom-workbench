"""桌面窗口模式：用 pywebview 把本地服务包成一个独立窗口。

双击 start.bat 走的入口。内部流程：

    起本地 HTTP 服务（127.0.0.1 随机可用端口，线程内）
        ↓
    pywebview 打开原生窗口（Windows 用 WebView2）
        ↓
    窗口关闭 → 服务停止 → 进程退出

原生能力通过 ``window.pywebview.api`` 暴露给前端：结果文件另存为、文本导出、
打开输出目录。前端检测不到该对象时（浏览器模式）自动回退为普通下载。

若 pywebview 或 WebView2 不可用，本模块会退化为「起服务 + 打开默认浏览器」，
保证双击始终能用。
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import time
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_DIR)

if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")

APP_TITLE = "PCBA BOM 工作台"
WINDOW_SIZE = (1460, 920)
WINDOW_MIN = (1080, 680)
PREFERRED_PORT = 8760


# ---------------------------------------------------------------------------
# 日志（pythonw 启动时没有控制台，输出全部落盘，便于排查）
# ---------------------------------------------------------------------------
def _log_file():
    log_dir = os.path.join(PROJECT_DIR, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        return None
    return os.path.join(log_dir, "desktop.log")


class _Tee:
    def __init__(self, *streams):
        self._streams = [s for s in streams if s]

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


_log_handle = None


def setup_logging() -> None:
    global _log_handle
    path = _log_file()
    if not path:
        return
    try:
        _log_handle = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    _log_handle.write("\n" + "=" * 60 + f"\n启动 {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    console = sys.stdout if getattr(sys, "stdout", None) else None
    errors = sys.stderr if getattr(sys, "stderr", None) else None
    sys.stdout = _Tee(console, _log_handle)
    sys.stderr = _Tee(errors, _log_handle)


def notify(message: str, title: str = APP_TITLE) -> None:
    """没有控制台时的兜底提示：优先原生消息框，其次控制台。"""
    print(message)
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)
    except Exception:
        pass


def focus_existing_window(title: str = APP_TITLE) -> bool:
    """把已经在运行的窗口切到前台（重复双击时的正确行为）。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE：最小化时也拉起来
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


ICON_PATH = os.path.join(BASE_DIR, "static", "assets", "app.ico")


def apply_window_icon(icon_path: str = ICON_PATH, title: str = APP_TITLE) -> bool:
    """把窗口/任务栏图标换成应用图标。

    pywebview 不支持在 Windows 上设置窗口图标，这里用 WM_SETICON 直接设。
    ctypes 必须显式声明 argtypes：句柄是 64 位，默认按 int 传会截断。
    """
    if sys.platform != "win32" or not os.path.exists(icon_path):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LPARAM

        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        done = False
        for size, which in ((16, 0), (32, 1)):   # ICON_SMALL / ICON_BIG
            hicon = user32.LoadImageW(None, icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if hicon:
                user32.SendMessageW(hwnd, WM_SETICON, which, hicon)
                done = True
        return done
    except Exception:
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# 启动就绪标记：start.bat 用它判断窗口是否真的起来了（pythonw 没有控制台）
# ---------------------------------------------------------------------------
READY_MARKER = os.path.join(PROJECT_DIR, "logs", "desktop.ready")


def mark_ready() -> None:
    try:
        os.makedirs(os.path.dirname(READY_MARKER), exist_ok=True)
        with open(READY_MARKER, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass


def clear_ready() -> None:
    try:
        os.remove(READY_MARKER)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 单实例：同一个工作区只允许一个窗口，避免重复双击开出两个实例
# ---------------------------------------------------------------------------
_instance_lock = None


def acquire_single_instance(workspace: str):
    """用文件锁防止重复启动。

    返回 True 表示本次启动成功拿到锁；False 表示已有实例在运行。
    锁由操作系统在进程结束时自动释放，所以不会出现「上次异常退出后永远起不来」。
    """
    global _instance_lock
    if sys.platform != "win32":
        return True

    import msvcrt

    try:
        os.makedirs(workspace, exist_ok=True)
        handle = open(os.path.join(workspace, "instance.lock"), "a+")
    except OSError:
        return True  # 拿不到锁文件就不阻塞启动

    # 必须先把读写位置归零再锁：a+ 模式初始位置在文件末尾，
    # 而首个实例会写入 pid 让文件变长，两端锁的就不是同一个字节了。
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return False

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _instance_lock = handle
    return True


# ---------------------------------------------------------------------------
# 本地服务
# ---------------------------------------------------------------------------
def free_port(preferred: int = PREFERRED_PORT) -> int:
    """优先用固定端口（便于排查），被占用时顺延，最后交给系统分配。"""
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ServerThread(threading.Thread):
    def __init__(self, flask_app, port: int):
        super().__init__(name="bom-http", daemon=True)
        from werkzeug.serving import make_server

        # 关掉 werkzeug 的请求日志：桌面模式下没有控制台，写日志只会拖慢交互
        import logging

        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self._server = make_server("127.0.0.1", port, flask_app, threaded=True)

    def run(self) -> None:
        self._server.serve_forever()

    def stop(self) -> None:
        try:
            self._server.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 暴露给前端的原生能力
# ---------------------------------------------------------------------------
class DesktopApi:
    """pywebview 会把本类实例挂在 ``window.pywebview.api`` 上。"""

    def __init__(self, store):
        self._store = store
        self._window = None

    def bind_window(self, window) -> None:
        self._window = window

    # -- 内部工具 ---------------------------------------------------------
    def _save_dialog(self, filename: str, file_types: tuple[str, ...]) -> str | None:
        import webview

        if self._window is None:
            return None
        picked = self._window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=filename, file_types=file_types
        )
        if not picked:
            return None
        return picked[0] if isinstance(picked, (list, tuple)) else str(picked)

    @staticmethod
    def _reveal(path: str) -> None:
        """在资源管理器中选中该文件（失败不影响保存结果）。"""
        if sys.platform != "win32" or not path or not os.path.exists(path):
            return
        try:
            import subprocess

            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception:
            pass

    # -- 前端可调用的方法 -------------------------------------------------
    def app_info(self) -> dict:
        return {
            "mode": "desktop",
            "title": APP_TITLE,
            "workspace": self._store.root,
            "outputs": self._store.outputs_dir,
            "uploads": self._store.uploads_dir,
        }

    def save_task_output(self, task_id: str) -> dict:
        """把某个任务的输出文件另存到用户指定位置。"""
        from app.core import jobs

        data = jobs.find(self._store, task_id)
        if not data or not data.get("output"):
            return {"ok": False, "error": "该任务没有可导出的结果文件"}
        source = data["output"]["path"]
        if not os.path.exists(source):
            return {"ok": False, "error": "结果文件已被移除，请重新执行"}

        name = os.path.basename(source)
        target = self._save_dialog(name, ("Excel 工作簿 (*.xlsx)", "所有文件 (*.*)"))
        if not target:
            return {"ok": False, "cancelled": True}
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            return {"ok": False, "error": f"写入失败：{exc}"}
        self._reveal(target)
        return {"ok": True, "path": target, "name": os.path.basename(target)}

    def save_text(self, filename: str, content: str) -> dict:
        """保存前端生成的文本（如待确认清单 CSV）。"""
        target = self._save_dialog(filename, ("CSV 文件 (*.csv)", "文本文件 (*.txt)",
                                              "所有文件 (*.*)"))
        if not target:
            return {"ok": False, "cancelled": True}
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write(content or "")
        except OSError as exc:
            return {"ok": False, "error": f"写入失败：{exc}"}
        self._reveal(target)
        return {"ok": True, "path": target, "name": os.path.basename(target)}

    def open_folder(self, kind: str = "outputs") -> dict:
        """打开工作区目录（outputs / uploads / workspace）。"""
        folder = {
            "outputs": self._store.outputs_dir,
            "uploads": self._store.uploads_dir,
        }.get(kind, self._store.root)
        if not os.path.isdir(folder):
            return {"ok": False, "error": "目录不存在"}
        try:
            os.startfile(folder)  # noqa: S606 - Windows 专用
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": folder}

    def open_result_folder(self) -> dict:
        return self.open_folder("outputs")


# ---------------------------------------------------------------------------
# 浏览器回退
# ---------------------------------------------------------------------------
def start_browser_server(flask_app, port: int) -> threading.Thread:
    """在后台线程里跑 Flask（浏览器回退路径用）。"""
    thread = threading.Thread(
        target=lambda: flask_app.run(host="127.0.0.1", port=port, debug=False, threaded=True),
        name="bom-http-fallback",
        daemon=True,
    )
    thread.start()
    return thread


def run_browser_fallback(flask_app, reason: str) -> int:
    """没有独立窗口时退化为「起服务 + 打开默认浏览器」，保证双击仍可用。"""
    import webbrowser

    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"[回退] {reason}")
    print(f"已改用浏览器方式启动：{url}")

    start_browser_server(flask_app, port)
    mark_ready()
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    # 消息框是模态的，放在最后：先让服务和浏览器就绪，再提示用户
    notify(f"{reason}\n\n已改用浏览器方式启动，请查看刚打开的浏览器窗口。\n{url}\n"
           f"（关闭本提示后程序仍在运行，可直接使用浏览器）")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    setup_logging()

    try:
        import webview
    except ImportError:
        webview = None

    from app.server import create_app

    app = create_app()
    store = app.extensions["store"]

    # 同一工作区只跑一个实例，避免重复双击开出两个窗口、并发写同一份状态
    if not acquire_single_instance(store.root):
        if focus_existing_window():
            print("已有实例在运行，已把它切到前台。")
        else:
            print("已有实例在运行，退出本次启动。")
            notify(f"{APP_TITLE} 已经在运行了。\n\n"
                   f"请在任务栏中切换到已打开的窗口。")
        return 0

    # 独立窗口不可用时不要先占端口，直接走浏览器回退
    if webview is None:
        return run_browser_fallback(app, "未安装 pywebview，无法创建独立窗口。")

    port = free_port()
    url = f"http://127.0.0.1:{port}/"

    server = ServerThread(app, port)
    server.start()

    # 等服务真正可连，避免窗口打开时白屏
    for _ in range(60):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)

    print(f"{APP_TITLE} 已启动：{url}")
    print(f"工作区：{store.root}")

    if webview is None:
        return run_browser_fallback(app, port, "未安装 pywebview，无法创建独立窗口。")

    api = DesktopApi(store)
    window = webview.create_window(
        APP_TITLE,
        url,
        js_api=api,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN,
        text_select=True,      # 数据工具必须允许选中/复制表格文本
        confirm_close=False,
    )
    api.bind_window(window)

    # 窗口真正显示出来后再落就绪标记，start.bat 依赖它判断启动成功
    def on_shown() -> None:
        mark_ready()
        if apply_window_icon():
            print("窗口图标已应用。")

    try:
        window.events.shown += on_shown
    except Exception:
        mark_ready()

    # Windows 上显式确认 WebView2 后端可用；不可用则交给 pywebview 自动选择
    gui = None
    if sys.platform == "win32":
        try:
            import webview.platforms.winforms  # noqa: F401

            gui = "edgechromium"
        except Exception:
            traceback.print_exc()
            print("WebView2 后端不可用，改用默认 GUI 后端。")

    try:
        webview.start(
            gui=gui,
            debug=False,
            private_mode=False,   # 保留 localStorage，主题等偏好跨次启动有效
            storage_path=os.path.join(PROJECT_DIR, "logs", "webview"),
        )
    except Exception as exc:
        traceback.print_exc()
        server.stop()
        clear_ready()
        return run_browser_fallback(app, f"独立窗口启动失败：{exc}")

    server.stop()
    clear_ready()
    print("窗口已关闭，服务已停止。")
    return 0


if __name__ == "__main__":
    exit_code = 0
    try:
        exit_code = main()
    except Exception as exc:  # 无控制台时用原生弹窗告知失败原因
        traceback.print_exc()
        notify(f"启动失败：{exc}\n\n详细信息见 logs\\desktop.log\n可尝试重新运行 安装.bat 修复运行环境。")
        exit_code = 1
    raise SystemExit(exit_code)
