"""Display and retain privacy-filtered, read-only connection diagnostics."""
from datetime import datetime, timezone
import json
import tkinter as tk
from tkinter import ttk
from uuid import uuid4

import runtime_paths


class ConnectionDiagnosticError(RuntimeError):
    """A connection refusal with pure diagnostic data supplied by the reader.

    Construction must stay free of filesystem and UI work: the exception can
    originate in the connection worker before it reaches the main Tk thread.
    """

    def __init__(self, message: str, diagnostic: dict):
        super().__init__(message)
        self.diagnostic = diagnostic


def show_connection_error(root, error: ConnectionDiagnosticError):
    """Show a copyable diagnostic and best-effort save only its supplied data."""
    diagnostic_text = json.dumps(error.diagnostic, ensure_ascii=False, indent=2)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    filename = f"connection-diagnostic-{stamp}-{uuid4().hex[:8]}.json"
    try:
        runtime_paths.LOG_ROOT.mkdir(parents=True, exist_ok=True)
        with (runtime_paths.LOG_ROOT / filename).open("x", encoding="utf-8") as output:
            output.write(diagnostic_text + "\n")
        saved_message = f"诊断已保存到日志目录：{filename}"
    except OSError:
        # A read-only directory or full disk must not hide the connection error.
        saved_message = "诊断文件未能保存；仍可使用“复制诊断”保留以下内容。"

    window = tk.Toplevel(root)
    window.title("连接游戏诊断")
    window.geometry("780x540")
    window.minsize(620, 440)
    window.transient(root)
    content = ttk.Frame(window, name="content", padding=14)
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=1)
    content.rowconfigure(1, weight=1)
    summary = ttk.Label(content, name="summary", text=f"连接未完成：{error}\n"
                        "请复制以下诊断，以便区分未找到类型、候选被拒绝或多个候选。",
                        wraplength=740, justify="left")
    summary.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    summary.bind("<Configure>", lambda event: summary.configure(wraplength=max(100, event.width)))
    details = tk.Text(content, name="diagnostic_text", wrap="word", font=("Consolas", 10),
                      width=1, height=12, padx=8, pady=8)
    details.grid(row=1, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(content, orient="vertical", command=details.yview)
    scrollbar.grid(row=1, column=1, sticky="ns")
    details.configure(yscrollcommand=scrollbar.set)
    details.insert("1.0", diagnostic_text)
    details.configure(state="disabled")
    status = ttk.Label(content, name="status", text=saved_message, wraplength=740, justify="left")
    status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 8))
    status.bind("<Configure>", lambda event: status.configure(wraplength=max(100, event.width)))
    actions = ttk.Frame(content, name="actions")
    actions.grid(row=3, column=0, columnspan=2, sticky="e")

    def copy_diagnostic():
        try:
            window.clipboard_clear()
            window.clipboard_append(diagnostic_text)
        except tk.TclError:
            status.configure(text="暂时无法写入剪贴板，请选中上方诊断后手动复制。")
        else:
            status.configure(text="诊断已复制。" + saved_message)

    ttk.Button(actions, name="copy", text="复制诊断", command=copy_diagnostic).pack(side="left", padx=(0, 8))
    ttk.Button(actions, name="close", text="关闭", command=window.destroy).pack(side="left")
    window.bind("<Escape>", lambda _event: window.destroy())
    window.grab_set()
    return window
