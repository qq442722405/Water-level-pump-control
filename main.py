import sys
import os
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import pygame
import datetime
from PIL import ImageGrab, Image, ImageTk
import pyautogui
from ocr import OcrReader

# -------------------- DPI 缩放兼容 (解决高分屏截图与点击错位问题) --------------------
def enable_dpi_awareness():
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

enable_dpi_awareness()

# -------------------- 资源路径解析 (兼容本地运行与 PyInstaller 打包) --------------------
def get_resource_path(relative_path):
    """获取静态资源的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# -------------------- 全局配置 --------------------
CONFIG_FILE = "config.json"
LOG_DIR = "logs"
MODEL_DIR = "models"
ASSETS_DIR = "assets"

DEFAULT_CONFIG = {
    "water_high": 120.0,
    "water_low": 90.0,
    "freq_high": 50.0,
    "freq_low": 35.0,
    "ocr_interval": 500,
    "adjust_delay": 3000,
    "alarm_count": 5,
    "loop_alarm": True,
    "mute": False,
    "alarm_sound": "Windows Notify.wav",
    "water_rect": [100, 100, 120, 35],
    "freq_rect": [350, 100, 120, 35],
    "point1": [1250, 560],
    "point2": [1320, 560],
    "easyocr_model": MODEL_DIR
}

config = DEFAULT_CONFIG.copy()
running = False
alarm_triggered = False
abnormal_count = 0
last_water_value = None
pyautogui.FAILSAFE = False

# -------------------- 工具函数 --------------------
def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        except Exception:
            save_config()
    else:
        save_config()

def save_config():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def init_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(LOG_DIR, "events.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass

def take_screenshot():
    filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_alarm.png"
    path = os.path.join(LOG_DIR, filename)
    try:
        ImageGrab.grab().save(path)
        log(f"截图已保存: {path}")
    except Exception as e:
        log(f"截图失败: {e}")

# -------------------- 报警声音 --------------------
WINDOWS_MEDIA = r"C:\Windows\Media"
SOUND_LIST = []
if os.path.exists(WINDOWS_MEDIA):
    for f in os.listdir(WINDOWS_MEDIA):
        if f.lower().endswith('.wav'):
            SOUND_LIST.append(f)
if not SOUND_LIST:
    SOUND_LIST = ["Windows Notify.wav", "Alarm01.wav", "Alarm02.wav"]

def get_alarm_path(filename):
    sys_path = os.path.join(WINDOWS_MEDIA, filename)
    if os.path.exists(sys_path):
        return sys_path
    assets_path = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(assets_path):
        return assets_path
    return None

def init_pygame_mixer():
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    except Exception as e:
        log(f"Pygame Mixer 初始化失败: {e}")

def play_alarm(loop=True):
    if config["mute"]:
        return
    path = get_alarm_path(config["alarm_sound"])
    if not path:
        return
    try:
        init_pygame_mixer()
        if loop:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1)
        else:
            sound = pygame.mixer.Sound(path)
            sound.play()
    except Exception as e:
        print(f"播放声音失败: {e}")

def stop_alarm():
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass

def test_sound():
    play_alarm(loop=False)

# -------------------- 屏幕区域 / 点选择 --------------------
def select_region_on_screen(callback, preview_widget=None):
    top = tk.Toplevel(root)
    top.attributes("-fullscreen", True)
    top.attributes("-alpha", 0.3)
    top.attributes("-topmost", True)
    top.configure(bg='black')

    canvas = tk.Canvas(top, highlightthickness=0, bg='black')
    canvas.pack(fill=tk.BOTH, expand=True)

    start_x = tk.IntVar()
    start_y = tk.IntVar()
    rect = None

    def close_window():
        try:
            top.grab_release()
        except Exception:
            pass
        top.destroy()

    def on_mouse_down(event):
        start_x.set(event.x_root)
        start_y.set(event.y_root)

    def on_mouse_move(event):
        nonlocal rect
        x1, y1 = start_x.get(), start_y.get()
        x2, y2 = event.x_root, event.y_root
        if rect:
            canvas.delete(rect)
        rect = canvas.create_rectangle(x1, y1, x2, y2, outline='red', width=2)

    def on_mouse_up(event):
        x1, y1 = start_x.get(), start_y.get()
        x2, y2 = event.x_root, event.y_root
        if x1 > x2: x1, x2 = x2, x1
        if y1 > y2: y1, y2 = y2, y1
        w = x2 - x1
        h = y2 - y1
        close_window()
        if w > 5 and h > 5:
            callback(x1, y1, w, h)
            if preview_widget:
                update_preview(preview_widget, (x1, y1, x1 + w, y1 + h))

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)
    top.bind("<Escape>", lambda e: close_window())

    top.focus_force()
    try:
        top.grab_set()
    except Exception:
        pass

def select_point_on_screen(callback):
    top = tk.Toplevel(root)
    top.attributes("-fullscreen", True)
    top.attributes("-alpha", 0.01)
    top.attributes("-topmost", True)
    top.configure(bg='black')

    def close_window():
        try:
            top.grab_release()
        except Exception:
            pass
        top.destroy()

    def on_click(event):
        x, y = event.x_root, event.y_root
        close_window()
        callback(x, y)

    top.bind("<Button-1>", on_click)
    top.bind("<Escape>", lambda e: close_window())
    top.focus_force()
    try:
        top.grab_set()
    except Exception:
        pass

def update_preview(label_widget, bbox):
    """更新屏幕框选区域的实时预览图像"""
    try:
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            return
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        img.thumbnail((200, 40), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        label_widget.configure(image=photo, text="")
        label_widget.image = photo
    except Exception:
        label_widget.configure(image='', text="预览无法显示")

# -------------------- UI 更新回调 --------------------
def update_water_rect(x, y, w, h):
    config["water_rect"] = [x, y, w, h]
    water_rect_label.config(text=f"区域: {x},{y} {w}x{h}")
    update_preview(water_preview, (x, y, x + w, y + h))
    save_config()

def update_freq_rect(x, y, w, h):
    config["freq_rect"] = [x, y, w, h]
    freq_rect_label.config(text=f"区域: {x},{y} {w}x{h}")
    update_preview(freq_preview, (x, y, x + w, y + h))
    save_config()

def update_point1(x, y):
    config["point1"] = [x, y]
    point1_label.config(text=f"坐标: {x},{y}")
    save_config()

def update_point2(x, y):
    config["point2"] = [x, y]
    point2_label.config(text=f"坐标: {x},{y}")
    save_config()

# -------------------- 控制逻辑后台线程 --------------------
def control_loop():
    global running, abnormal_count, last_water_value, alarm_triggered
    try:
        reader = OcrReader(config.get("easyocr_model", MODEL_DIR))
    except Exception as e:
        root.after(0, messagebox.showerror, "模型错误", f"无法加载 OCR 模型: {e}")
        root.after(0, stop_loop)
        return

    while running:
        wr = config["water_rect"]
        fr = config["freq_rect"]
        try:
            water_img = ImageGrab.grab(bbox=(wr[0], wr[1], wr[0]+wr[2], wr[1]+wr[3]))
            freq_img = ImageGrab.grab(bbox=(fr[0], fr[1], fr[0]+fr[2], fr[1]+fr[3]))
        except Exception as e:
            log(f"截图失败: {e}")
            time.sleep(config["ocr_interval"] / 1000.0)
            continue

        water_val = reader.read_number(water_img)
        freq_val = reader.read_number(freq_img)

        root.after(0, update_display, water_val, freq_val)

        if water_val is None or freq_val is None:
            time.sleep(config["ocr_interval"] / 1000.0)
            continue

        need_click = None
        if water_val > config["water_high"] and freq_val < config["freq_high"]:
            need_click = "point1"
        elif water_val < config["water_low"] and freq_val > config["freq_low"]:
            need_click = "point2"

        if need_click:
            point = config["point1"] if need_click == "point1" else config["point2"]
            pyautogui.click(point[0], point[1])
            log(f"液位 {water_val:.1f}，频率 {freq_val:.1f}，点击 {need_click}，等待 {config['adjust_delay']}ms")
            time.sleep(config["adjust_delay"] / 1000.0)
        else:
            if water_val > config["water_high"]:
                log(f"液位超标但频率已达上限 {freq_val:.1f}，不操作")
            elif water_val < config["water_low"]:
                log(f"液位过低但频率已达下限 {freq_val:.1f}，不操作")

        if water_val > config["water_high"] or water_val < config["water_low"]:
            if last_water_value is not None and (
                (last_water_value > config["water_high"] and water_val > config["water_high"]) or
                (last_water_value < config["water_low"] and water_val < config["water_low"])
            ):
                abnormal_count += 1
            else:
                abnormal_count = 1
            last_water_value = water_val
        else:
            abnormal_count = 0
            last_water_value = None
            if alarm_triggered:
                stop_alarm()
                alarm_triggered = False

        if abnormal_count >= config["alarm_count"] and not alarm_triggered:
            log(f"连续异常次数达到 {abnormal_count}，触发报警")
            root.after(0, trigger_alarm)
            alarm_triggered = True

        time.sleep(config["ocr_interval"] / 1000.0)

def update_display(water, freq):
    water_label.config(text=f"{water:.1f}" if water is not None else "识别失败")
    freq_label.config(text=f"{freq:.1f}" if freq is not None else "识别失败")
    status_label.config(text="报警中" if alarm_triggered else "正常",
                        foreground="red" if alarm_triggered else "green")
    count_label.config(text=str(abnormal_count))

def trigger_alarm():
    play_alarm(loop=config["loop_alarm"])
    take_screenshot()
    try:
        from win10toast import ToastNotifier
        threading.Thread(target=lambda: ToastNotifier().show_toast("液位控制报警", "连续异常次数达到设定值！", duration=3), daemon=True).start()
    except Exception:
        pass

def start_loop():
    global running
    if not running:
        running = True
        threading.Thread(target=control_loop, daemon=True).start()
        start_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)

def stop_loop():
    global running, alarm_triggered
    running = False
    stop_alarm()
    alarm_triggered = False
    start_btn.config(state=tk.NORMAL)
    stop_btn.config(state=tk.DISABLED)

# -------------------- 参数保存与恢复 --------------------
def save_all_settings():
    try:
        config["water_high"] = float(water_high_entry.get())
        config["water_low"] = float(water_low_entry.get())
        config["freq_high"] = float(freq_high_entry.get())
        config["freq_low"] = float(freq_low_entry.get())
        config["ocr_interval"] = int(ocr_interval_entry.get())
        config["adjust_delay"] = int(adjust_delay_entry.get())
        config["alarm_count"] = int(alarm_count_entry.get())
        config["loop_alarm"] = loop_var.get()
        config["mute"] = mute_var.get()
        config["alarm_sound"] = alarm_sound_var.get()
        save_config()
        messagebox.showinfo("成功", "设置已保存！")
    except ValueError:
        messagebox.showerror("错误", "请输入有效的数字参数")

def restore_defaults():
    global config
    config = DEFAULT_CONFIG.copy()
    update_ui_from_config()
    save_config()
    messagebox.showinfo("恢复", "已恢复默认设置")

def update_ui_from_config():
    entries_map = [
        (water_high_entry, "water_high"),
        (water_low_entry, "water_low"),
        (freq_high_entry, "freq_high"),
        (freq_low_entry, "freq_low"),
        (ocr_interval_entry, "ocr_interval"),
        (adjust_delay_entry, "adjust_delay"),
        (alarm_count_entry, "alarm_count")
    ]
    for entry, key in entries_map:
        entry.delete(0, tk.END)
        entry.insert(0, str(config[key]))

    loop_var.set(config["loop_alarm"])
    mute_var.set(config["mute"])
    sound = config["alarm_sound"]
    alarm_sound_var.set(sound if sound in SOUND_LIST else SOUND_LIST[0])

    wr = config["water_rect"]
    water_rect_label.config(text=f"区域: {wr[0]},{wr[1]} {wr[2]}x{wr[3]}")
    update_preview(water_preview, (wr[0], wr[1], wr[0] + wr[2], wr[1] + wr[3]))

    fr = config["freq_rect"]
    freq_rect_label.config(text=f"区域: {fr[0]},{fr[1]} {fr[2]}x{fr[3]}")
    update_preview(freq_preview, (fr[0], fr[1], fr[0] + fr[2], fr[1] + fr[3]))

    p1 = config["point1"]
    point1_label.config(text=f"坐标: {p1[0]},{p1[1]}")
    p2 = config["point2"]
    point2_label.config(text=f"坐标: {p2[0]},{p2[1]}")

# -------------------- 构建 GUI 界面 --------------------
init_dirs()
load_config()

root = tk.Tk()
root.title("水位水泵控制 V2.0")
root.geometry("460x700")
root.resizable(True, True)

# 图标加载 (兼容 PyInstaller 解压环境)
icon_path = get_resource_path("1.ico")
if os.path.exists(icon_path):
    try:
        root.iconbitmap(icon_path)
    except Exception:
        pass

# 顶部标题
tk.Label(root, text="水位水泵控制系统 V2.0", font=("Microsoft YaHei", 13, "bold")).pack(pady=6)

# 1. 实时 OCR & 预览区域
ocr_frame = tk.LabelFrame(root, text="实时 OCR & 预览", padx=10, pady=6)
ocr_frame.pack(fill=tk.X, padx=12, pady=4)

# 液位行
row_w = tk.Frame(ocr_frame)
row_w.pack(fill=tk.X, pady=2)
tk.Label(row_w, text="液位：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
water_label = tk.Label(row_w, text="--", fg="blue", font=("Microsoft YaHei", 10, "bold"))
water_label.pack(side=tk.LEFT, padx=5)
water_rect_label = tk.Label(row_w, text="区域: --", fg="gray", font=("Microsoft YaHei", 9))
water_rect_label.pack(side=tk.LEFT, padx=5)
tk.Button(row_w, text="选择区域", command=lambda: select_region_on_screen(update_water_rect, water_preview)).pack(side=tk.RIGHT)

water_preview = tk.Label(ocr_frame, text="液位截图预览", bg="#EAEAEA", height=2)
water_preview.pack(fill=tk.X, pady=3)

# 频率行
row_f = tk.Frame(ocr_frame)
row_f.pack(fill=tk.X, pady=2)
tk.Label(row_f, text="频率：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
freq_label = tk.Label(row_f, text="--", fg="blue", font=("Microsoft YaHei", 10, "bold"))
freq_label.pack(side=tk.LEFT, padx=5)
freq_rect_label = tk.Label(row_f, text="区域: --", fg="gray", font=("Microsoft YaHei", 9))
freq_rect_label.pack(side=tk.LEFT, padx=5)
tk.Button(row_f, text="选择区域", command=lambda: select_region_on_screen(update_freq_rect, freq_preview)).pack(side=tk.RIGHT)

freq_preview = tk.Label(ocr_frame, text="频率截图预览", bg="#EAEAEA", height=2)
freq_preview.pack(fill=tk.X, pady=3)

# 状态行
row_s = tk.Frame(ocr_frame)
row_s.pack(fill=tk.X, pady=3)
tk.Label(row_s, text="状态：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
status_label = tk.Label(row_s, text="正常", fg="green", font=("Microsoft YaHei", 9, "bold"))
status_label.pack(side=tk.LEFT, padx=5)
tk.Label(row_s, text="连续异常：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=(25, 0))
count_label = tk.Label(row_s, text="0", fg="red", font=("Microsoft YaHei", 9, "bold"))
count_label.pack(side=tk.LEFT)

# 2. 参数设置 (改进为两列 Grid 排版，不再错位)
param_frame = tk.LabelFrame(root, text="参数设置", padx=10, pady=6)
param_frame.pack(fill=tk.X, padx=12, pady=4)

params_def = [
    ("液位上限：", "water_high"),
    ("液位下限：", "water_low"),
    ("频率上限：", "freq_high"),
    ("频率下限：", "freq_low"),
    ("检测间隔(ms)：", "ocr_interval"),
    ("调整等待(ms)：", "adjust_delay"),
    ("报警次数：", "alarm_count")
]

entries = {}
for i, (label_text, key) in enumerate(params_def):
    r = i // 2
    c = (i % 2) * 2
    tk.Label(param_frame, text=label_text, anchor="e", font=("Microsoft YaHei", 9)).grid(row=r, column=c, sticky="e", padx=2, pady=2)
    entry = tk.Entry(param_frame, width=10)
    entry.grid(row=r, column=c+1, sticky="w", padx=4, pady=2)
    entries[key] = entry

water_high_entry = entries["water_high"]
water_low_entry = entries["water_low"]
freq_high_entry = entries["freq_high"]
freq_low_entry = entries["freq_low"]
ocr_interval_entry = entries["ocr_interval"]
adjust_delay_entry = entries["adjust_delay"]
alarm_count_entry = entries["alarm_count"]

# 3. 报警设置
alarm_frame = tk.LabelFrame(root, text="报警设置", padx=10, pady=6)
alarm_frame.pack(fill=tk.X, padx=12, pady=4)

row_a1 = tk.Frame(alarm_frame)
row_a1.pack(fill=tk.X, pady=2)
tk.Label(row_a1, text="声音文件：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
alarm_sound_var = tk.StringVar(value=SOUND_LIST[0])
sound_combo = ttk.Combobox(row_a1, textvariable=alarm_sound_var, values=SOUND_LIST, state="readonly", width=20)
sound_combo.pack(side=tk.LEFT, padx=5)
tk.Button(row_a1, text="试听", command=test_sound).pack(side=tk.LEFT, padx=5)

row_a2 = tk.Frame(alarm_frame)
row_a2.pack(fill=tk.X, pady=2)
loop_var = tk.BooleanVar(value=True)
tk.Checkbutton(row_a2, text="循环报警", variable=loop_var, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=5)
mute_var = tk.BooleanVar(value=False)
tk.Checkbutton(row_a2, text="静音模式", variable=mute_var, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=20)

# 4. 操作坐标
coord_frame = tk.LabelFrame(root, text="操作坐标", padx=10, pady=6)
coord_frame.pack(fill=tk.X, padx=12, pady=4)

row_c1 = tk.Frame(coord_frame)
row_c1.pack(fill=tk.X, pady=2)
tk.Button(row_c1, text="选择减频坐标", command=lambda: select_point_on_screen(update_point1)).pack(side=tk.LEFT)
point1_label = tk.Label(row_c1, text="坐标: --", fg="gray", font=("Microsoft YaHei", 9))
point1_label.pack(side=tk.LEFT, padx=10)

row_c2 = tk.Frame(coord_frame)
row_c2.pack(fill=tk.X, pady=2)
tk.Button(row_c2, text="选择加频坐标", command=lambda: select_point_on_screen(update_point2)).pack(side=tk.LEFT)
point2_label = tk.Label(row_c2, text="坐标: --", fg="gray", font=("Microsoft YaHei", 9))
point2_label.pack(side=tk.LEFT, padx=10)

# 5. 底部控制按钮
ctrl_frame = tk.Frame(root)
ctrl_frame.pack(fill=tk.X, padx=12, pady=10)

start_btn = tk.Button(ctrl_frame, text="启动", command=start_loop, width=8, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 9, "bold"))
start_btn.pack(side=tk.LEFT, padx=4)
stop_btn = tk.Button(ctrl_frame, text="停止", command=stop_loop, state=tk.DISABLED, width=8, bg="#F44336", fg="white", font=("Microsoft YaHei", 9, "bold"))
stop_btn.pack(side=tk.LEFT, padx=4)
tk.Button(ctrl_frame, text="保存设置", command=save_all_settings, width=10, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=4)
tk.Button(ctrl_frame, text="恢复默认", command=restore_defaults, width=10, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=4)

# 读取配置并应用到 UI
update_ui_from_config()

# 启动 GUI 主循环
root.mainloop()
