#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海兹解压 - HaiZiJieYa
支持 7z / rar / zip / tar.gz 等格式的密码压缩包自动解压工具
内嵌 7-Zip 引擎，无需安装，可在任意电脑运行
密码本：txt 文件，一行一个密码
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
import time
import tempfile
import atexit

# ─── 右键菜单注册 (Windows Registry) ──────────────────────────────────────────
REG_KEY_FILE   = r"Software\Classes\*\shell\AutoUnzip"
REG_KEY_FOLDER = r"Software\Classes\Directory\shell\AutoUnzip"
MENU_LABEL = "🔐 海兹解压（密码解压）"

def get_exe_path():
    """获取当前可执行文件路径（支持 PyInstaller 打包后的 exe）"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)

def _reg_write(key_path, exe_path, label):
    """写注册表项（HKCU，不需要管理员权限）"""
    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, label)
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, f'"{exe_path}",0')
        winreg.CloseKey(k)
        cmd_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
        winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, f'"{exe_path}" --extract "%1"')
        winreg.CloseKey(cmd_key)
        return True, ""
    except Exception as e:
        return False, str(e)

def _reg_delete(key_path):
    """删除注册表项"""
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        return True, ""
    except FileNotFoundError:
        return True, ""
    except Exception as e:
        return False, str(e)

def _reg_exists(key_path):
    """检查注册表项是否存在"""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.CloseKey(k)
        return True
    except Exception:
        return False

def register_context_menu(exe_path=None):
    if exe_path is None:
        exe_path = get_exe_path()
    ok1, e1 = _reg_write(REG_KEY_FILE,   exe_path, MENU_LABEL)
    ok2, e2 = _reg_write(REG_KEY_FOLDER, exe_path, MENU_LABEL + " (文件夹内全部)")
    if ok1 and ok2:
        return True, "右键菜单注册成功！\n右击压缩文件或文件夹即可看到「海兹解压」菜单项。"
    return False, f"注册失败：{e1 or e2}"

def unregister_context_menu():
    ok1, e1 = _reg_delete(REG_KEY_FILE)
    ok2, e2 = _reg_delete(REG_KEY_FOLDER)
    if ok1 and ok2:
        return True, "右键菜单已移除。"
    return False, f"注销失败：{e1 or e2}"

def context_menu_registered():
    return _reg_exists(REG_KEY_FILE)

# ─── 配置路径 ──────────────────────────────────────────────────────────────────
def get_app_dir():
    """返回 exe 所在目录（打包后）或脚本目录（开发时）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(os.path.dirname(os.path.abspath(__file__)))

APP_DIR = get_app_dir()
CONFIG_FILE = APP_DIR / "auto_unzip_config.json"
DEFAULT_PWD_FILE = APP_DIR / "passwords.txt"

SEVEN_ZIP_PATHS = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
]

# ─── 内嵌 7-Zip 释放（PyInstaller 打包支持） ──────────────────────────────────
_bundled_7zip_dir = None  # 临时目录，程序退出时清理

def get_bundled_7zip():
    """
    从 PyInstaller 的 _MEIPASS 目录中找到内嵌的 7z.exe。
    首次调用时复制到临时目录（避免权限问题），并注册退出清理。
    """
    global _bundled_7zip_dir

    # 开发模式：直接用项目目录里的 7z.exe
    if not getattr(sys, 'frozen', False):
        local = Path(os.path.dirname(os.path.abspath(__file__))) / "7z.exe"
        if local.exists():
            return str(local)
        return None

    # 打包模式：_MEIPASS 下有内嵌的 7z.exe
    meipass = Path(sys._MEIPASS)  # type: ignore
    src_exe = meipass / "7z.exe"
    src_dll = meipass / "7z.dll"

    if not src_exe.exists():
        return None

    # 已经释放过，直接返回
    if _bundled_7zip_dir and Path(_bundled_7zip_dir, "7z.exe").exists():
        return str(Path(_bundled_7zip_dir) / "7z.exe")

    # 首次：复制到用户临时目录（一次性，程序退出自动清理）
    try:
        tmp_dir = tempfile.mkdtemp(prefix="autounzip_7z_")
        _bundled_7zip_dir = tmp_dir
        shutil.copy2(str(src_exe), tmp_dir)
        if src_dll.exists():
            shutil.copy2(str(src_dll), tmp_dir)
        atexit.register(_cleanup_bundled_7zip)
        return str(Path(tmp_dir) / "7z.exe")
    except Exception:
        # 复制失败，直接用 _MEIPASS 路径
        return str(src_exe)

def _cleanup_bundled_7zip():
    """程序退出时清理临时目录"""
    global _bundled_7zip_dir
    if _bundled_7zip_dir and Path(_bundled_7zip_dir).exists():
        try:
            shutil.rmtree(_bundled_7zip_dir, ignore_errors=True)
        except Exception:
            pass

def _set_window_icon(root):
    """为窗口设置图标（使用 ICO 文件，兼容开发/打包模式）"""
    try:
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent

        ico_path = base_dir / "app_icon.ico"
        if ico_path.exists():
            root.iconbitmap(str(ico_path))
    except Exception:
        pass

SUPPORTED_EXTS = {".7z", ".rar", ".zip", ".tar", ".gz", ".bz2", ".xz", ".tar.gz", ".tar.bz2", ".tar.xz", ".001"}

# ─── 颜色主题 ──────────────────────────────────────────────────────────────────
THEME = {
    "bg": "#1a1a2e",
    "card": "#16213e",
    "accent": "#0f3460",
    "highlight": "#e94560",
    "success": "#4ade80",
    "warning": "#fbbf24",
    "error": "#f87171",
    "text": "#e2e8f0",
    "text_dim": "#94a3b8",
    "border": "#334155",
    "input_bg": "#0f172a",
    "btn_hover": "#1e40af",
}

# ─── 密码本管理 ────────────────────────────────────────────────────────────────
def load_passwords_from_file(txt_path):
    """从 txt 文件加载密码列表（去空行、去重、保持顺序）"""
    p = Path(txt_path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        seen = set()
        result = []
        for line in lines:
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                result.append(line)
        return result
    except Exception:
        return []

def save_passwords_to_file(txt_path, passwords):
    """将密码列表保存到 txt 文件"""
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(passwords))
        return True
    except Exception:
        return False

def ensure_default_pwd_file():
    """确保默认密码本文件存在"""
    if not DEFAULT_PWD_FILE.exists():
        try:
            with open(DEFAULT_PWD_FILE, "w", encoding="utf-8") as f:
                f.write("# 每行一个密码，# 开头的行为注释\n")
        except Exception:
            pass
    return str(DEFAULT_PWD_FILE)

# ─── 配置管理 ──────────────────────────────────────────────────────────────────
def load_config():
    default = {
        "password_file": str(DEFAULT_PWD_FILE),
        "delete_after_extract": False,
        "extract_to_subfolder": True,
        "last_output_dir": "",
        "seven_zip_path": "",
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default.update(saved)
        except Exception:
            pass
    return default

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存配置失败: {e}")

def find_7zip():
    # 1. 优先使用内嵌版本（打包进 exe 的 7z.exe，无需安装）
    bundled = get_bundled_7zip()
    if bundled and Path(bundled).exists():
        return bundled
    # 2. 系统安装路径
    for p in SEVEN_ZIP_PATHS:
        if Path(p).exists():
            return p
    # 3. PATH 环境变量
    result = shutil.which("7z")
    if result:
        return result
    return None

# ─── 解压核心逻辑 ──────────────────────────────────────────────────────────────
def is_archive(filepath):
    p = Path(filepath)
    name_lower = p.name.lower()
    for ext in [".tar.gz", ".tar.bz2", ".tar.xz"]:
        if name_lower.endswith(ext):
            return True
    return p.suffix.lower() in SUPPORTED_EXTS

def get_archive_name(filepath):
    """获取不带扩展名的文件名（处理复合扩展名）"""
    p = Path(filepath)
    name = p.name
    for ext in [".tar.gz", ".tar.bz2", ".tar.xz"]:
        if name.lower().endswith(ext):
            return name[:-len(ext)]
    return p.stem

def try_extract(seven_zip, archive_path, output_dir, password=None):
    """尝试解压，返回 (success: bool, error_msg: str)"""
    cmd = [seven_zip, "x", str(archive_path), f"-o{output_dir}", "-y", "-aoa"]
    if password:
        cmd.append(f"-p{password}")
    else:
        cmd.append("-p")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        stdout = result.stdout + result.stderr
        if result.returncode == 0:
            return True, ""
        elif result.returncode == 1:
            if "Wrong password" in stdout or "Cannot open encrypted archive" in stdout:
                return False, "密码错误"
            return True, "警告(部分文件可能有问题)"
        else:
            if "Wrong password" in stdout or "Encrypted" in stdout or "wrong password" in stdout.lower():
                return False, "密码错误"
            return False, f"解压失败(退出码{result.returncode}): {stdout[-300:]}"
    except subprocess.TimeoutExpired:
        return False, "解压超时(超过5分钟)"
    except Exception as e:
        return False, str(e)

def extract_with_passwords(seven_zip, archive_path, output_dir, passwords, progress_cb=None):
    """依次尝试密码列表，返回 (success, used_password, message)"""
    archive_path = str(archive_path)

    # 先尝试无密码
    if progress_cb:
        progress_cb("正在尝试无密码解压...")
    success, msg = try_extract(seven_zip, archive_path, output_dir, password=None)
    if success:
        return True, None, msg

    # 过滤注释行再尝试
    valid_pwds = [p for p in passwords if p and not p.startswith("#")]
    for i, pwd in enumerate(valid_pwds):
        if progress_cb:
            progress_cb(f"正在尝试密码 [{i+1}/{len(valid_pwds)}]: {pwd[:3]}***")
        success, msg = try_extract(seven_zip, archive_path, output_dir, password=pwd)
        if success:
            return True, pwd, msg

    return False, None, "所有密码均尝试失败，需要手动输入密码"

# ─── 主界面 ────────────────────────────────────────────────────────────────────
class AutoUnzipApp:
    def __init__(self, root):
        self.root = root
        self.root.title("海兹解压 - HaiZiJieYa")
        self.root.geometry("960x740")
        self.root.configure(bg=THEME["bg"])
        self.root.resizable(True, True)
        self.root.minsize(760, 580)
        _set_window_icon(self.root)

        self.config = load_config()
        # 确保密码本文件存在
        ensure_default_pwd_file()
        if not self.config.get("password_file"):
            self.config["password_file"] = str(DEFAULT_PWD_FILE)

        self.seven_zip = self.config.get("seven_zip_path") or find_7zip()
        self.running = False
        self.cancel_flag = False
        self.file_queue = []

        self._setup_styles()
        self._build_ui()
        self._check_7zip()

        try:
            self.root.drop_target_register('DND_Files')  # type: ignore
            self.root.dnd_bind('<<Drop>>', self._on_drop)  # type: ignore
        except Exception:
            pass

    # ── 样式 ──
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Card.TFrame", background=THEME["card"])
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"], font=("微软雅黑", 10))
        style.configure("Card.TLabel", background=THEME["card"], foreground=THEME["text"], font=("微软雅黑", 10))
        style.configure("Title.TLabel", background=THEME["bg"], foreground=THEME["text"], font=("微软雅黑", 14, "bold"))
        style.configure("Dim.TLabel", background=THEME["card"], foreground=THEME["text_dim"], font=("微软雅黑", 9))
        style.configure("TCheckbutton", background=THEME["card"], foreground=THEME["text"], font=("微软雅黑", 10))
        style.map("TCheckbutton", background=[("active", THEME["card"])])
        style.configure("Horizontal.TProgressbar",
                        background=THEME["highlight"],
                        troughcolor=THEME["input_bg"],
                        borderwidth=0,
                        thickness=8)

    # ── UI 构建 ──
    def _build_ui(self):
        # 标题栏（固定高度）
        title_frame = tk.Frame(self.root, bg=THEME["accent"], height=56)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text="海兹解压", font=("微软雅黑", 15, "bold"),
                 bg=THEME["accent"], fg="white").pack(side="left", padx=20, pady=12)
        tk.Label(title_frame, text="支持 7z · rar · zip · tar.gz 等格式  |  内嵌引擎，无需安装 7-Zip",
                 font=("微软雅黑", 9), bg=THEME["accent"], fg="#93c5fd").pack(side="left", pady=12)

        # 内容区容器（fill=both expand=True，填满标题栏下方所有空间）
        body = tk.Frame(self.root, bg=THEME["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # 左列（左侧区域，自然高度，不向上下扩展）
        left = tk.Frame(body, bg=THEME["bg"])
        left.pack(side="left", fill="both", padx=(0, 8))

        self._build_file_section(left)
        self._build_options_section(left)
        self._build_context_menu_section(left)
        self._build_action_buttons(left)

        # 右列 - 密码本管理（右侧固定宽度）
        right = tk.Frame(body, bg=THEME["bg"])
        right.pack(side="right", fill="both", padx=(8, 0))
        right.configure(width=260)
        right.pack_propagate(False)
        self._build_password_section(right)

        # 日志区（在 body 容器内，可伸缩填满剩余空间）
        self._build_log_section(body)

    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=THEME["border"], bd=0)
        outer.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(outer, bg=THEME["card"], bd=0)
        inner.pack(fill="x", padx=1, pady=1)
        if title:
            tk.Label(inner, text=title, font=("微软雅黑", 10, "bold"),
                     bg=THEME["card"], fg=THEME["highlight"]).pack(anchor="w", padx=12, pady=(10, 4))
        return inner

    def _build_file_section(self, parent):
        card = self._card(parent, "📁 压缩文件")

        drop_frame = tk.Frame(card, bg=THEME["input_bg"], relief="flat", bd=0,
                               highlightthickness=1, highlightbackground=THEME["border"])
        drop_frame.pack(fill="x", padx=12, pady=(0, 8))
        self.drop_label = tk.Label(drop_frame,
                                    text="📂 拖放压缩文件到此处，或点击下方按钮选择文件",
                                    font=("微软雅黑", 9), bg=THEME["input_bg"],
                                    fg=THEME["text_dim"], wraplength=340, pady=14)
        self.drop_label.pack()

        list_frame = tk.Frame(card, bg=THEME["card"])
        list_frame.pack(fill="x", padx=12, pady=(0, 4))
        scrollbar = tk.Scrollbar(list_frame, bg=THEME["card"])
        scrollbar.pack(side="right", fill="y")
        self.file_listbox = tk.Listbox(list_frame, height=5,
                                        bg=THEME["input_bg"], fg=THEME["text"],
                                        selectbackground=THEME["accent"],
                                        font=("微软雅黑", 9),
                                        borderwidth=0, highlightthickness=0,
                                        yscrollcommand=scrollbar.set)
        self.file_listbox.pack(fill="x")
        scrollbar.config(command=self.file_listbox.yview)

        btn_row = tk.Frame(card, bg=THEME["card"])
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        self._btn(btn_row, "➕ 添加文件", self._add_files, color=THEME["accent"]).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "📂 添加文件夹", self._add_folder, color=THEME["accent"]).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "🗑 清空", self._clear_files, color="#374151").pack(side="left")

        tk.Label(card, text="输出目录（留空则解压到原文件夹）：",
                 font=("微软雅黑", 9), bg=THEME["card"], fg=THEME["text_dim"]).pack(anchor="w", padx=12)
        out_row = tk.Frame(card, bg=THEME["card"])
        out_row.pack(fill="x", padx=12, pady=(2, 12))
        self.output_var = tk.StringVar(value=self.config.get("last_output_dir", ""))
        tk.Entry(out_row, textvariable=self.output_var, bg=THEME["input_bg"],
                 fg=THEME["text"], insertbackground="white",
                 font=("微软雅黑", 9), relief="flat", bd=4).pack(side="left", fill="x", expand=True)
        self._btn(out_row, "浏览", self._browse_output, color=THEME["accent"], pad=(4, 0)).pack(side="right")

    def _build_options_section(self, parent):
        card = self._card(parent, "⚙️ 解压选项")
        inner = tk.Frame(card, bg=THEME["card"])
        inner.pack(fill="x", padx=12, pady=(0, 12))

        self.subfolder_var = tk.BooleanVar(value=self.config.get("extract_to_subfolder", True))
        self.delete_var = tk.BooleanVar(value=self.config.get("delete_after_extract", False))

        cb1 = tk.Checkbutton(inner, text="📁 解压到同名子文件夹（推荐）",
                              variable=self.subfolder_var,
                              bg=THEME["card"], fg=THEME["text"],
                              selectcolor=THEME["input_bg"],
                              activebackground=THEME["card"],
                              font=("微软雅黑", 10))
        cb1.pack(anchor="w", pady=2)

        cb2 = tk.Checkbutton(inner, text="🗑 解压成功后删除原压缩文件",
                              variable=self.delete_var,
                              bg=THEME["card"], fg=THEME["text"],
                              selectcolor=THEME["input_bg"],
                              activebackground=THEME["card"],
                              font=("微软雅黑", 10))
        cb2.pack(anchor="w", pady=2)

        tk.Label(inner, text="⚠ 删除操作不可恢复，请确认文件已完整解压再使用",
                 font=("微软雅黑", 8), bg=THEME["card"], fg=THEME["warning"]).pack(anchor="w", pady=(2, 0))

    def _build_context_menu_section(self, parent):
        card = self._card(parent, "🖱️ 右键菜单集成")
        inner = tk.Frame(card, bg=THEME["card"])
        inner.pack(fill="x", padx=12, pady=(0, 12))

        self.ctx_status_var = tk.StringVar()
        self.ctx_status_label = tk.Label(inner, textvariable=self.ctx_status_var,
                                          font=("微软雅黑", 9), bg=THEME["card"],
                                          fg=THEME["text_dim"], wraplength=300, justify="left")
        self.ctx_status_label.pack(anchor="w", pady=(0, 6))
        self._refresh_ctx_status()

        btn_row = tk.Frame(inner, bg=THEME["card"])
        btn_row.pack(fill="x")
        self.reg_btn = self._btn(btn_row, "✅ 注册右键菜单", self._register_ctx, color="#166534")
        self.reg_btn.pack(side="left", padx=(0, 6))
        self.unreg_btn = self._btn(btn_row, "❌ 移除右键菜单", self._unregister_ctx, color="#7f1d1d")
        self.unreg_btn.pack(side="left")

        tk.Label(inner,
                 text="右键调用时固定行为：解压到同名文件夹 + 成功后删除原压缩包",
                 font=("微软雅黑", 8), bg=THEME["card"], fg=THEME["text_dim"],
                 justify="left").pack(anchor="w", pady=(6, 0))

        # 更新状态标签显示新名称
        self.ctx_status_label.config(wraplength=300)

    def _refresh_ctx_status(self):
        if context_menu_registered():
            self.ctx_status_var.set("● 右键菜单：已注册（对所有压缩文件生效）")
            self.ctx_status_label.config(fg=THEME["success"])
        else:
            self.ctx_status_var.set("○ 右键菜单：未注册")
            self.ctx_status_label.config(fg=THEME["text_dim"])

    def _register_ctx(self):
        exe = get_exe_path()
        ok, msg = register_context_menu(exe)
        self._refresh_ctx_status()
        if ok:
            messagebox.showinfo("注册成功", msg)
            self._log(f"✅ 右键菜单注册成功: {exe}", "success")
        else:
            messagebox.showerror("注册失败", msg)
            self._log(f"❌ 右键菜单注册失败: {msg}", "error")

    def _unregister_ctx(self):
        if not messagebox.askyesno("确认", "确定要移除右键菜单吗？"):
            return
        ok, msg = unregister_context_menu()
        self._refresh_ctx_status()
        if ok:
            messagebox.showinfo("已移除", msg)
            self._log("✅ 右键菜单已移除", "warning")
        else:
            messagebox.showerror("移除失败", msg)
            self._log(f"❌ 右键菜单移除失败: {msg}", "error")

    def _build_action_buttons(self, parent):
        frame = tk.Frame(parent, bg=THEME["bg"])
        frame.pack(fill="x", pady=(0, 6))

        self.start_btn = self._btn(frame, "▶  开始解压", self._start_extract,
                                    color=THEME["highlight"], pad=(0, 8))
        self.start_btn.pack(side="left", padx=(0, 8), ipady=6, ipadx=10)

        self.cancel_btn = self._btn(frame, "⏹ 取消", self._cancel,
                                     color="#374151", pad=(0, 8))
        self.cancel_btn.pack(side="left", ipady=6, ipadx=6)
        self.cancel_btn.config(state="disabled")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(parent, variable=self.progress_var,
                                             maximum=100, style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(4, 0))

        self.progress_label = tk.Label(parent, text="就绪",
                                        font=("微软雅黑", 9), bg=THEME["bg"], fg=THEME["text_dim"])
        self.progress_label.pack(anchor="w")

    # ── 密码本面板 ──
    def _build_password_section(self, parent):
        card = self._card(parent, "🔑 密码本")
        card.pack(fill="both", expand=True)

        # 密码本路径选择
        tk.Label(card, text="密码本文件 (.txt)：",
                 font=("微软雅黑", 8), bg=THEME["card"], fg=THEME["text_dim"]).pack(anchor="w", padx=10, pady=(4,0))

        path_row = tk.Frame(card, bg=THEME["card"])
        path_row.pack(fill="x", padx=10, pady=(2, 4))

        self.pwd_file_var = tk.StringVar(value=self.config.get("password_file", str(DEFAULT_PWD_FILE)))
        pwd_entry = tk.Entry(path_row, textvariable=self.pwd_file_var,
                              bg=THEME["input_bg"], fg=THEME["text"],
                              insertbackground="white",
                              font=("微软雅黑", 8), relief="flat", bd=3)
        pwd_entry.pack(side="left", fill="x", expand=True)
        self._btn(path_row, "…", self._browse_pwd_file,
                  color=THEME["accent"], pad=(0, 0)).pack(side="right", padx=(3, 0))

        # 操作按钮行
        action_row = tk.Frame(card, bg=THEME["card"])
        action_row.pack(fill="x", padx=10, pady=(0, 4))
        self._btn(action_row, "🔄 重新加载", self._reload_passwords,
                  color=THEME["accent"]).pack(side="left", padx=(0, 4))
        self._btn(action_row, "✏️ 编辑文件", self._open_pwd_file,
                  color="#374151").pack(side="left")

        # 密码列表预览（只读）
        tk.Label(card, text="密码预览（加载自文件）：",
                 font=("微软雅黑", 8), bg=THEME["card"], fg=THEME["text_dim"]).pack(anchor="w", padx=10, pady=(4,0))

        list_frame = tk.Frame(card, bg=THEME["card"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=(2, 4))

        sb = tk.Scrollbar(list_frame, bg=THEME["card"])
        sb.pack(side="right", fill="y")

        self.pwd_listbox = tk.Listbox(list_frame,
                                       bg=THEME["input_bg"], fg=THEME["text"],
                                       selectbackground=THEME["accent"],
                                       font=("Consolas", 10),
                                       borderwidth=0, highlightthickness=0,
                                       yscrollcommand=sb.set,
                                       state="normal")
        self.pwd_listbox.pack(fill="both", expand=True)
        sb.config(command=self.pwd_listbox.yview)

        # 快速添加单条密码
        tk.Label(card, text="快速追加密码：",
                 font=("微软雅黑", 8), bg=THEME["card"], fg=THEME["text_dim"]).pack(anchor="w", padx=10, pady=(6,0))

        quick_row = tk.Frame(card, bg=THEME["card"])
        quick_row.pack(fill="x", padx=10, pady=(2, 4))
        self.quick_pwd_var = tk.StringVar()
        quick_entry = tk.Entry(quick_row, textvariable=self.quick_pwd_var,
                                bg=THEME["input_bg"], fg=THEME["text"],
                                insertbackground="white", show="•",
                                font=("Consolas", 11), relief="flat", bd=4)
        quick_entry.pack(fill="x")
        quick_entry.bind("<Return>", lambda e: self._quick_add_password())

        self.show_quick_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="显示密码", variable=self.show_quick_var,
                        command=lambda: quick_entry.config(show="" if self.show_quick_var.get() else "•"),
                        bg=THEME["card"], fg=THEME["text_dim"],
                        selectcolor=THEME["input_bg"],
                        activebackground=THEME["card"],
                        font=("微软雅黑", 8)).pack(anchor="w", padx=10)

        self._btn(card, "➕ 追加到密码本", self._quick_add_password,
                  color=THEME["success"]).pack(fill="x", padx=10, pady=(2, 10))

        # 计数标签
        self.pwd_count_var = tk.StringVar()
        tk.Label(card, textvariable=self.pwd_count_var,
                 font=("微软雅黑", 8), bg=THEME["card"], fg=THEME["text_dim"]).pack(anchor="w", padx=10, pady=(0, 6))

        # 加载密码列表
        self._reload_passwords()

    def _reload_passwords(self):
        """从 txt 文件重新加载密码到预览列表"""
        pwd_file = self.pwd_file_var.get().strip()
        self.config["password_file"] = pwd_file
        self.passwords = load_passwords_from_file(pwd_file)
        self.pwd_listbox.delete(0, tk.END)
        for p in self.passwords:
            if p.startswith("#"):
                self.pwd_listbox.insert(tk.END, p)
                self.pwd_listbox.itemconfig(tk.END, fg=THEME["text_dim"])
            else:
                self.pwd_listbox.insert(tk.END, p)
        valid = [p for p in self.passwords if not p.startswith("#")]
        self.pwd_count_var.set(f"共 {len(valid)} 条有效密码（{len(self.passwords)} 行）")
        save_config(self.config)

    def _browse_pwd_file(self):
        """浏览选择密码本文件"""
        path = filedialog.askopenfilename(
            title="选择密码本文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialdir=str(APP_DIR)
        )
        if path:
            self.pwd_file_var.set(path)
            self._reload_passwords()
            self._log(f"📖 已加载密码本: {Path(path).name}，{len(self.passwords)} 条记录", "info")

    def _open_pwd_file(self):
        """用记事本打开密码本文件（方便直接编辑）"""
        pwd_file = self.pwd_file_var.get().strip()
        if not pwd_file:
            messagebox.showwarning("提示", "请先选择密码本文件")
            return
        p = Path(pwd_file)
        if not p.exists():
            # 创建空文件
            try:
                p.write_text("# 每行一个密码，# 开头的行为注释\n", encoding="utf-8")
            except Exception:
                pass
        try:
            os.startfile(str(p))
            messagebox.showinfo("提示", f"已用记事本打开密码本：\n{p}\n\n编辑保存后，点击「🔄 重新加载」使更改生效。")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件: {e}")

    def _quick_add_password(self):
        """快速追加单条密码到 txt 文件"""
        pwd = self.quick_pwd_var.get().strip()
        if not pwd:
            return
        pwd_file = self.pwd_file_var.get().strip()
        if not pwd_file:
            messagebox.showwarning("提示", "请先设置密码本文件路径")
            return

        # 检查是否重复
        current = load_passwords_from_file(pwd_file)
        if pwd in current:
            messagebox.showwarning("提示", "该密码已存在于密码本中")
            return

        # 追加写入
        try:
            with open(pwd_file, "a", encoding="utf-8") as f:
                if current:
                    f.write(f"\n{pwd}")
                else:
                    f.write(pwd)
            self.quick_pwd_var.set("")
            self._reload_passwords()
            self._log(f"💾 已追加密码到密码本: {pwd[:3]}***", "success")
        except Exception as e:
            messagebox.showerror("写入失败", str(e))

    def _build_log_section(self, parent):
        log_frame = tk.Frame(parent, bg=THEME["bg"])
        log_frame.pack(fill="both", expand=True, pady=(8, 0))

        tk.Label(log_frame, text="📋 解压日志", font=("微软雅黑", 10, "bold"),
                 bg=THEME["bg"], fg=THEME["text_dim"]).pack(anchor="w")

        text_frame = tk.Frame(log_frame, bg=THEME["border"], bd=0)
        text_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(text_frame)
        sb.pack(side="right", fill="y")

        self.log_text = tk.Text(text_frame,
                                 bg=THEME["input_bg"], fg=THEME["text"],
                                 font=("Consolas", 9), relief="flat",
                                 wrap="word", state="disabled",
                                 yscrollcommand=sb.set,
                                 borderwidth=0, padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)
        sb.config(command=self.log_text.yview)

        self.log_text.tag_configure("success", foreground=THEME["success"])
        self.log_text.tag_configure("error", foreground=THEME["error"])
        self.log_text.tag_configure("warning", foreground=THEME["warning"])
        self.log_text.tag_configure("info", foreground=THEME["text_dim"])
        self.log_text.tag_configure("highlight", foreground=THEME["highlight"])

    # ── 辅助 UI 方法 ──
    def _btn(self, parent, text, cmd, color=None, pad=(0, 0)):
        color = color or THEME["accent"]
        btn = tk.Button(parent, text=text, command=cmd,
                        bg=color, fg="white",
                        font=("微软雅黑", 9, "bold"),
                        relief="flat", cursor="hand2",
                        padx=pad[0]+8, pady=pad[1]+3,
                        activebackground=THEME["btn_hover"],
                        activeforeground="white",
                        borderwidth=0)
        return btn

    def _log(self, msg, tag="info"):
        self.log_text.config(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _set_progress(self, pct, status=""):
        self.progress_var.set(pct)
        if status:
            self.progress_label.config(text=status)

    # ── 文件操作 ──
    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="选择压缩文件",
            filetypes=[
                ("压缩文件", "*.7z *.rar *.zip *.tar *.gz *.bz2 *.xz *.001"),
                ("所有文件", "*.*"),
            ]
        )
        for f in files:
            if f not in self.file_queue:
                self.file_queue.append(f)
                self.file_listbox.insert(tk.END, Path(f).name)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="选择包含压缩文件的文件夹")
        if not folder:
            return
        count = 0
        for root, _, files in os.walk(folder):
            for fname in files:
                fpath = os.path.join(root, fname)
                if is_archive(fpath) and fpath not in self.file_queue:
                    self.file_queue.append(fpath)
                    self.file_listbox.insert(tk.END, Path(fpath).name)
                    count += 1
        self._log(f"从文件夹添加了 {count} 个压缩文件", "info")

    def _clear_files(self):
        self.file_queue.clear()
        self.file_listbox.delete(0, tk.END)

    def _browse_output(self):
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_var.set(folder)

    def _on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        for f in files:
            if os.path.isfile(f) and is_archive(f) and f not in self.file_queue:
                self.file_queue.append(f)
                self.file_listbox.insert(tk.END, Path(f).name)
            elif os.path.isdir(f):
                for root, _, fnames in os.walk(f):
                    for fname in fnames:
                        fp = os.path.join(root, fname)
                        if is_archive(fp) and fp not in self.file_queue:
                            self.file_queue.append(fp)
                            self.file_listbox.insert(tk.END, Path(fp).name)

    # ── 解压控制 ──
    def _check_7zip(self):
        if not self.seven_zip or not Path(self.seven_zip).exists():
            self._log("❌ 内嵌 7-Zip 引擎异常，请重新下载本工具", "error")
            messagebox.showerror("引擎异常",
                                  "内嵌的 7-Zip 引擎文件异常。\n"
                                  "请尝试重新下载本工具。\n\n"
                                  "（备用方案：安装系统版 7-Zip https://7-zip.org）")
        else:
            # 判断是内嵌还是系统版
            bundled = get_bundled_7zip()
            if bundled and Path(bundled).exists() and self.seven_zip == bundled:
                self._log(f"✓ 内嵌 7-Zip 引擎就绪（无需安装，可在任意电脑使用）", "success")
            else:
                self._log(f"✓ 使用系统 7-Zip: {self.seven_zip}", "success")
            pwd_file = self.pwd_file_var.get()
            self._log(f"📖 密码本: {pwd_file}（{len([p for p in self.passwords if not p.startswith('#')])} 条有效密码）", "info")

    def _start_extract(self):
        if not self.seven_zip or not Path(self.seven_zip).exists():
            messagebox.showerror("错误", "未找到 7-Zip，无法解压")
            return
        if not self.file_queue:
            messagebox.showwarning("提示", "请先添加压缩文件")
            return

        # 每次开始前重新加载密码本
        self._reload_passwords()

        self.config["delete_after_extract"] = self.delete_var.get()
        self.config["extract_to_subfolder"] = self.subfolder_var.get()
        self.config["last_output_dir"] = self.output_var.get()
        save_config(self.config)

        self.running = True
        self.cancel_flag = False
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        thread = threading.Thread(target=self._extract_worker, daemon=True)
        thread.start()

    def _cancel(self):
        self.cancel_flag = True
        self._log("⏹ 用户取消解压...", "warning")

    def _extract_worker(self):
        total = len(self.file_queue)
        success_count = 0
        fail_count = 0
        failed_files = []

        self.root.after(0, lambda: self._log(f"▶ 开始处理 {total} 个文件...", "highlight"))

        for i, archive_path in enumerate(list(self.file_queue)):
            if self.cancel_flag:
                break

            filename = Path(archive_path).name
            pct = (i / total) * 100
            self.root.after(0, lambda p=pct, f=filename: self._set_progress(p, f"处理: {f}"))
            self.root.after(0, lambda f=filename, idx=i: self._log(f"📦 [{idx+1}/{total}] {f}", "info"))

            archive_dir = str(Path(archive_path).parent)
            custom_out = self.output_var.get().strip()
            if custom_out and os.path.isdir(custom_out):
                base_out = custom_out
            else:
                base_out = archive_dir

            if self.subfolder_var.get():
                output_dir = os.path.join(base_out, get_archive_name(archive_path))
            else:
                output_dir = base_out

            def progress_cb(msg, idx=i):
                self.root.after(0, lambda m=msg: self._set_progress(
                    ((idx + 0.5) / total) * 100, m))

            ok, used_pwd, msg = extract_with_passwords(
                self.seven_zip, archive_path, output_dir,
                self.passwords, progress_cb
            )

            if not ok and "需要手动输入密码" in msg:
                self.root.after(0, lambda f=filename, ap=archive_path, od=output_dir:
                                self._ask_manual_password(f, ap, od))
                fail_count += 1
                failed_files.append(filename)
                self.root.after(0, lambda f=filename: self._log(
                    f"  ❌ {f} — 所有密码均失败，请手动解压", "error"))
                continue

            if ok:
                success_count += 1
                pwd_info = f"（使用密码: {used_pwd[:3]}***）" if used_pwd else "（无密码）"
                if msg and "警告" in msg:
                    self.root.after(0, lambda f=filename, pi=pwd_info:
                                    self._log(f"  ⚠ {f} — 解压完成但有警告 {pi}", "warning"))
                else:
                    self.root.after(0, lambda f=filename, pi=pwd_info:
                                    self._log(f"  ✓ {f} — 解压成功 {pi}", "success"))

                if self.delete_var.get():
                    try:
                        os.remove(archive_path)
                        self.root.after(0, lambda f=filename:
                                        self._log(f"    🗑 已删除: {f}", "warning"))
                    except Exception as e:
                        self.root.after(0, lambda f=filename, err=str(e):
                                        self._log(f"    ⚠ 删除 {f} 失败: {err}", "error"))
            else:
                fail_count += 1
                failed_files.append(filename)
                self.root.after(0, lambda f=filename, m=msg:
                                self._log(f"  ❌ {f} — {m}", "error"))

        pct = 100 if not self.cancel_flag else (success_count + fail_count) / total * 100
        summary = f"完成！成功 {success_count}/{total}"
        if fail_count > 0:
            summary += f"，失败 {fail_count} 个"

        self.root.after(0, lambda: self._set_progress(pct, summary))
        self.root.after(0, lambda: self._log(
            f"\n{'=' * 40}\n{summary}", "highlight" if fail_count == 0 else "warning"))

        if failed_files:
            self.root.after(0, lambda: self._log(
                "失败文件：\n" + "\n".join(f"  • {f}" for f in failed_files), "error"))

        self.running = False
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.cancel_btn.config(state="disabled"))

    def _ask_manual_password(self, filename, archive_path, output_dir):
        pwd = simpledialog.askstring(
            "需要密码",
            f"所有已保存密码均无效。\n\n文件: {filename}\n\n请手动输入密码:",
            show="•"
        )
        if pwd:
            ok, used, msg = extract_with_passwords(
                self.seven_zip, archive_path, output_dir, [pwd])
            if ok:
                self._log(f"  ✓ {filename} — 手动输入密码解压成功", "success")
                if messagebox.askyesno("保存密码", f"密码 '{pwd[:3]}***' 有效，是否追加到密码本？"):
                    pwd_file = self.pwd_file_var.get().strip()
                    current = load_passwords_from_file(pwd_file)
                    if pwd not in current:
                        try:
                            with open(pwd_file, "a", encoding="utf-8") as f:
                                f.write(f"\n{pwd}")
                            self._reload_passwords()
                            self._log(f"  💾 密码已追加到密码本: {pwd[:3]}***", "success")
                        except Exception as e:
                            self._log(f"  ⚠ 写入密码本失败: {e}", "error")
                if self.delete_var.get():
                    try:
                        os.remove(archive_path)
                        self._log(f"  🗑 已删除: {filename}", "warning")
                    except Exception:
                        pass
            else:
                self._log(f"  ❌ {filename} — 手动密码仍错误", "error")


# ─── 右键菜单模式（固定行为） ──────────────────────────────────────────────────
def cli_extract(archive_path):
    """
    命令行模式：被右键菜单调用。
    固定行为：解压到同名文件夹 + 成功后删除原压缩包。
    显示简洁进度窗口，全部成功后3秒自动关闭。
    """
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    cfg = load_config()
    seven_zip = cfg.get("seven_zip_path") or find_7zip()

    # 从配置中的密码本文件加载密码
    pwd_file = cfg.get("password_file") or str(DEFAULT_PWD_FILE)
    passwords = load_passwords_from_file(pwd_file)

    root = tk.Tk()
    root.title("海兹解压 - 处理中...")
    root.geometry("500x320")
    root.resizable(False, False)
    root.configure(bg=THEME["bg"])
    _set_window_icon(root)

    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"500x320+{(sw-500)//2}+{(sh-320)//2}")

    tk.Label(root, text="海兹解压", font=("微软雅黑", 13, "bold"),
             bg=THEME["bg"], fg="white").pack(pady=(18, 4))

    valid_pwd_count = len([p for p in passwords if not p.startswith("#")])
    tk.Label(root, text=f"密码本：{Path(pwd_file).name}  ({valid_pwd_count} 条密码)",
             font=("微软雅黑", 8), bg=THEME["bg"], fg=THEME["text_dim"]).pack(pady=(0, 2))

    path_label = tk.Label(root, text=Path(archive_path).name,
                           font=("微软雅黑", 9), bg=THEME["bg"],
                           fg=THEME["text_dim"], wraplength=460)
    path_label.pack(pady=(0, 6))

    status_var = tk.StringVar(value="正在准备...")
    status_label = tk.Label(root, textvariable=status_var,
                             font=("微软雅黑", 10), bg=THEME["bg"], fg=THEME["text"])
    status_label.pack(pady=(0, 8))

    progress_var = tk.DoubleVar(value=0)
    ttk.Style().configure("Horizontal.TProgressbar",
                           background=THEME["highlight"],
                           troughcolor=THEME["input_bg"],
                           borderwidth=0, thickness=10)
    bar = ttk.Progressbar(root, variable=progress_var, maximum=100,
                           style="Horizontal.TProgressbar", length=440)
    bar.pack(pady=(0, 10))

    result_label = tk.Label(root, text="", font=("微软雅黑", 9),
                             bg=THEME["bg"], fg=THEME["text_dim"], wraplength=460)
    result_label.pack()

    close_btn = tk.Button(root, text="关闭", state="disabled",
                           command=root.destroy,
                           bg=THEME["accent"], fg="white",
                           font=("微软雅黑", 9, "bold"),
                           relief="flat", cursor="hand2",
                           padx=20, pady=4)
    close_btn.pack(pady=(10, 0))

    def worker():
        if not seven_zip or not Path(seven_zip).exists():
            root.after(0, lambda: status_var.set("❌ 内嵌引擎异常，请重新下载本工具"))
            root.after(0, lambda: status_label.config(fg=THEME["error"]))
            root.after(0, lambda: close_btn.config(state="normal"))
            return

        # 收集目标文件
        targets = []
        p = Path(archive_path)
        if p.is_dir():
            for root_dir, _, files in os.walk(str(p)):
                for fname in files:
                    fp = os.path.join(root_dir, fname)
                    if is_archive(fp):
                        targets.append(fp)
        elif p.is_file() and is_archive(str(p)):
            targets.append(str(p))

        if not targets:
            root.after(0, lambda: status_var.set("⚠ 未找到受支持的压缩文件"))
            root.after(0, lambda: status_label.config(fg=THEME["warning"]))
            root.after(0, lambda: close_btn.config(state="normal"))
            return

        total = len(targets)
        success_count = 0
        fail_count = 0

        for i, ap in enumerate(targets):
            fname = Path(ap).name
            root.after(0, lambda f=fname, idx=i:
                       status_var.set(f"[{idx+1}/{total}] 处理: {f}"))
            root.after(0, lambda idx=i: progress_var.set((idx / total) * 100))

            # 固定行为：解压到同名文件夹
            archive_dir = str(Path(ap).parent)
            out_dir = os.path.join(archive_dir, get_archive_name(ap))

            def prog_cb(msg, f=fname):
                root.after(0, lambda m=msg: status_var.set(m))

            ok, used_pwd, msg = extract_with_passwords(
                seven_zip, ap, out_dir, passwords, prog_cb)

            if ok:
                success_count += 1
                # 固定行为：成功后删除原压缩包
                try:
                    os.remove(ap)
                except Exception:
                    pass
            else:
                fail_count += 1

        root.after(0, lambda: progress_var.set(100))

        if fail_count == 0:
            summary = f"✅ 全部完成！成功解压 {success_count} 个文件，原压缩包已删除"
            root.after(0, lambda: status_var.set(summary))
            root.after(0, lambda: status_label.config(fg=THEME["success"]))
            root.after(0, lambda: close_btn.config(state="normal"))
            root.after(3000, root.destroy)
        else:
            summary = f"⚠ 完成：成功 {success_count}，失败 {fail_count}"
            root.after(0, lambda: status_var.set(summary))
            root.after(0, lambda: status_label.config(fg=THEME["warning"]))
            root.after(0, lambda: result_label.config(
                text="部分文件密码错误，请打开主程序更新密码本后重试",
                fg=THEME["warning"]))
            root.after(0, lambda: close_btn.config(state="normal"))

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    args = sys.argv[1:]

    # 右键菜单调用：--extract <path>
    if len(args) >= 2 and args[0] == "--extract":
        cli_extract(args[1])
        return

    # 拖拽到 exe 上：直接传入单个路径
    if len(args) == 1 and Path(args[0]).exists():
        root = tk.Tk()
        app = AutoUnzipApp(root)
        p = Path(args[0])
        if p.is_dir():
            for root_dir, _, files in os.walk(str(p)):
                for fname in files:
                    fp = os.path.join(root_dir, fname)
                    if is_archive(fp) and fp not in app.file_queue:
                        app.file_queue.append(fp)
                        app.file_listbox.insert(tk.END, Path(fp).name)
        elif p.is_file() and is_archive(str(p)):
            app.file_queue.append(str(p))
            app.file_listbox.insert(tk.END, p.name)
        root.protocol("WM_DELETE_WINDOW", lambda: (save_config(app.config), root.destroy()))
        root.mainloop()
        return

    # 正常打开
    root = tk.Tk()
    app = AutoUnzipApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (save_config(app.config), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
