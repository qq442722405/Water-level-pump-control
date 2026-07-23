import sys
import os
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import json
import pygame
import datetime
from PIL import ImageGrab, Image, ImageTk
import pyautogui
from ocr import OcrReader

# -------------------- DPI 缩放兼容 --------------------
def enable_dpi_awareness():
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

enable_dpi_awareness()

# -------------------- 路径与默认配置 --------------------
def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

CONFIG_FILE = "config.json"
LOG_DIR = "logs"
MODEL_DIR = "models"
ASSETS_DIR = "assets"

DEFAULT_CONFIG = {
    "water_mid": 105.0,
    "water_high": 120.0,
    "water_low": 90.0,
    "freq_high": 50.0,
    "freq_low": 35.0,
    "ocr_interval": 5000,  # 默认 5 秒 (5000ms)
    "loop_alarm": True,
    "mute": False,
    "alarm_sound": "Windows Notify.wav",
    "water_rect": [100, 100, 120, 35],
    "freq_rect": [350, 100, 120, 35],
    "point1": [1250, 560],  # 减频坐标
    "point2": [1320, 560],  # 加频坐标
    # 图像预处理参数
    "ocr_scale": 2.0,
    "ocr_contrast": 1.5,
    "ocr_invert": False,
    "ocr_sharpen": True,
    "ocr_blur": 0,
    "ocr_binarize": False,
    "ocr_thresh": 0,
    "ocr_morph": 0,
    "easyocr_model": MODEL_DIR
}

config = DEFAULT_CONFIG.copy()
running = False
alarm_triggered = False
pyautogui.FAILSAFE = False

# 小窗口全局控件句柄
mini_win = None
mini_water_label = None
mini_freq_label = None
mini_status_label = None
mini_start_btn = None
mini_stop_btn = None

# -------------------- 配置与日志 --------------------
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

def append_log(msg):
    """同时写入文本日志与 GUI 诊断日志框"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"

    log_file = os.path.join(LOG_DIR, "events.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

    def update_text_ui():
        if 'log_box' in globals() and log_box.winfo_exists():
            log_box.insert(tk.END, formatted_msg + "\n")
            log_box.see(tk.END)

    if root:
        root.after(0, update_text_ui)

# -------------------- 报警音频 --------------------
WINDOWS_MEDIA = r"C:\Windows\Media"
SOUND_LIST = []
if os.path.exists(WINDOWS_MEDIA):
    for f in os.listdir(WINDOWS_MEDIA):
        if f.lower().endswith('.wav'):
            SOUND_LIST.append(f)
if not SOUND_LIST:
    SOUND_LIST = ["Windows Notify.wav", "Alarm01.wav"]

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
        append_log(f"Pygame Mixer 初始化失败: {e}")

def play_alarm(sound_filename=None, loop=True):
    if config["mute"]:
        return
    snd_name = sound_filename if sound_filename else config["alarm_sound"]
    path = get_alarm_path(snd_name)
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
        print(f"播放音频异常: {e}")

def stop_alarm():
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass

def on_mute_toggle():
    """实时响应静音勾选/取消勾选"""
    config["mute"] = mute_var.get()
    if config["mute"]:
        stop_alarm()
        append_log("[静音] 已开启静音，强行切断报警音")
    else:
        append_log("[静音] 已取消静音")
        if alarm_triggered:
            play_alarm(loop=config["loop_alarm"])

def test_sound():
    play_alarm(sound_filename=alarm_sound_var.get(), loop=False)

# -------------------- 交互选择坐标/区域 --------------------
def select_region_on_screen(callback):
    top = tk.Toplevel(root)
    top.attributes("-fullscreen", True)
    top.attributes("-alpha", 0.3)
    top.attributes("-topmost", True)
    top.configure(bg='black')

    canvas = tk.Canvas(top, highlightthickness=0, bg='black')
    canvas.pack(fill=tk.BOTH, expand=True)

    start_x, start_y = tk.IntVar(), tk.IntVar()
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
        w, h = x2 - x1, y2 - y1
        close_window()
        if w > 5 and h > 5:
            callback(x1, y1, w, h)

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

# -------------------- 图像预览放大逻辑 --------------------
def update_processed_preview(label_widget, processed_img):
    try:
        if processed_img is None:
            return
        img = Image.fromarray(processed_img)
        w, h = img.width, img.height
        if w == 0 or h == 0:
            return

        target_h = 65
        scale_factor = target_h / float(h)
        target_w = int(w * scale_factor)

        if target_w > 480:
            target_w = 480

        img_resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img_resized)

        label_widget.configure(image=photo, text="")
        label_widget.image = photo
    except Exception:
        label_widget.configure(image='', text="预览生成失败")

# -------------------- UI 坐标更新 --------------------
def update_water_rect(x, y, w, h):
    config["water_rect"] = [x, y, w, h]
    water_rect_label.config(text=f"区域: {x},{y} {w}x{h}")
    append_log(f"更新液位区域: [{x}, {y}, {w}, {h}]")
    save_config()

def update_freq_rect(x, y, w, h):
    config["freq_rect"] = [x, y, w, h]
    freq_rect_label.config(text=f"区域: {x},{y} {w}x{h}")
    append_log(f"更新频率区域: [{x}, {y}, {w}, {h}]")
    save_config()

def update_point1(x, y):
    config["point1"] = [x, y]
    point1_label.config(text=f"坐标: {x},{y}")
    append_log(f"更新减频(点1)坐标: [{x}, {y}]")
    save_config()

def update_point2(x, y):
    config["point2"] = [x, y]
    point2_label.config(text=f"坐标: {x},{y}")
    append_log(f"更新加频(点2)坐标: [{x}, {y}]")
    save_config()

# -------------------- 后台核心控制线程 --------------------
def control_loop():
    global running, alarm_triggered
    try:
        reader = OcrReader(config.get("easyocr_model", MODEL_DIR))
        append_log("OCR 模型初始化成功，进入控制循环...")
    except Exception as e:
        root.after(0, messagebox.showerror, "模型加载错误", str(e))
        append_log(f"OCR 模型加载失败: {e}")
        root.after(0, stop_loop)
        return

    while running:
        wr = config["water_rect"]
        fr = config["freq_rect"]
        try:
            water_img = ImageGrab.grab(bbox=(wr[0], wr[1], wr[0]+wr[2], wr[1]+wr[3]))
            freq_img = ImageGrab.grab(bbox=(fr[0], fr[1], fr[0]+fr[2], fr[1]+fr[3]))
        except Exception as e:
            append_log(f"截图失败: {e}")
            time.sleep(config["ocr_interval"] / 1000.0)
            continue

        scale = float(config.get("ocr_scale", 2.0))
        contrast = float(config.get("ocr_contrast", 1.5))
        invert = bool(config.get("ocr_invert", False))
        sharpen = bool(config.get("ocr_sharpen", True))
        blur_k = int(config.get("ocr_blur", 0))
        binarize = bool(config.get("ocr_binarize", False))
        thresh_val = int(config.get("ocr_thresh", 0))
        morph_val = int(config.get("ocr_morph", 0))

        water_val, water_raw, proc_water_img = reader.read_number(
            water_img, scale, contrast, invert, blur_k, sharpen, binarize, thresh_val, morph_val
        )
        freq_val, freq_raw, proc_freq_img = reader.read_number(
            freq_img, scale, contrast, invert, blur_k, sharpen, binarize, thresh_val, morph_val
        )

        root.after(0, update_display, water_val, water_raw, freq_val, freq_raw, proc_water_img, proc_freq_img)

        if water_val is None or freq_val is None:
            append_log(f"[未识别跳过] 液位原始: '{water_raw}', 频率原始: '{freq_raw}'")
            time.sleep(config["ocr_interval"] / 1000.0)
            continue

        water_mid = config.get("water_mid", 105.0)
        freq_high = config.get("freq_high", 50.0)
        freq_low = config.get("freq_low", 35.0)

        need_click = None

        if water_val > water_mid:
            if freq_val < freq_high:
                need_click = "point2"  # 加频
            else:
                append_log(f"[极限拦截] 液位({water_val:.1f}) > 中间值({water_mid:.1f})，当前频率({freq_val:.1f})已达上限({freq_high:.1f})，拒绝加频！")

        elif water_val < water_mid:
            if freq_val > freq_low:
                need_click = "point1"  # 减频
            else:
                append_log(f"[极限拦截] 液位({water_val:.1f}) < 中间值({water_mid:.1f})，当前频率({freq_val:.1f})已达下限({freq_low:.1f})，拒绝减频！")

        else:
            append_log(f"[维持现状] 液位({water_val:.1f}) 正好等于目标值({water_mid:.1f})")

        if need_click:
            point = config["point2"] if need_click == "point2" else config["point1"]
            action_name = "加频(点2)" if need_click == "point2" else "减频(点1)"
            pyautogui.click(point[0], point[1])
            append_log(f"[执行控制] 液位:{water_val:.1f}(目标:{water_mid:.1f}), 频率:{freq_val:.1f} -> 点击【{action_name}】{point}")

        # 报警检测
        is_water_abnormal = (water_val > config["water_high"] or water_val < config["water_low"])
        is_freq_abnormal = (freq_val > config["freq_high"] or freq_val < config["freq_low"])

        if is_water_abnormal or is_freq_abnormal:
            append_log(f"[警报] 参数异常！液位:{water_val:.1f}, 频率:{freq_val:.1f}")
            if not alarm_triggered:
                root.after(0, trigger_alarm)
                alarm_triggered = True
        else:
            if alarm_triggered:
                stop_alarm()
                alarm_triggered = False
                append_log("[恢复] 参数恢复正常，已停止报警")

        # 严格控制休眠间隔
        time.sleep(config["ocr_interval"] / 1000.0)

def update_display(water, water_raw, freq, freq_raw, proc_water_img, proc_freq_img):
    # 更新主界面数值
    if water is not None:
        water_label.config(text=f"{water:.1f}", fg="blue")
    else:
        water_label.config(text=f"未识别 [{water_raw}]", fg="red")

    if freq is not None:
        freq_label.config(text=f"{freq:.1f}", fg="blue")
    else:
        freq_label.config(text=f"未识别 [{freq_raw}]", fg="red")

    status_label.config(text="报警中" if alarm_triggered else "正常",
                        foreground="red" if alarm_triggered else "green")

    # 同步更新小窗口数值
    if mini_water_label and mini_water_label.winfo_exists():
        w_txt = f"{water:.1f}" if water is not None else "未识别"
        mini_water_label.config(text=f"液位: {w_txt}")
    if mini_freq_label and mini_freq_label.winfo_exists():
        f_txt = f"{freq:.1f}" if freq is not None else "未识别"
        mini_freq_label.config(text=f"频率: {f_txt}")
    if mini_status_label and mini_status_label.winfo_exists():
        mini_status_label.config(text="状态: 报警中" if alarm_triggered else "状态: 正常",
                                 fg="red" if alarm_triggered else "green")

    # 更新预览图
    update_processed_preview(water_preview, proc_water_img)
    update_processed_preview(freq_preview, proc_freq_img)

def trigger_alarm():
    play_alarm(loop=config["loop_alarm"])

# -------------------- 实时同步 UI 到 config --------------------
def sync_ui_to_config():
    """在启动系统或保存时，立即将界面上的当前值同步进 config 内存对象"""
    try:
        config["water_mid"] = float(water_mid_entry.get())
        config["water_high"] = float(water_high_entry.get())
        config["water_low"] = float(water_low_entry.get())
        config["freq_high"] = float(freq_high_entry.get())
        config["freq_low"] = float(freq_low_entry.get())
        config["ocr_interval"] = int(ocr_interval_entry.get())

        config["ocr_scale"] = float(scale_entry.get())
        config["ocr_contrast"] = float(contrast_entry.get())
        config["ocr_invert"] = invert_var.get()
        config["ocr_sharpen"] = sharpen_var.get()
        config["ocr_blur"] = int(blur_entry.get())
        config["ocr_binarize"] = binarize_var.get()
        config["ocr_thresh"] = int(thresh_entry.get())
        config["ocr_morph"] = int(morph_entry.get())

        config["loop_alarm"] = loop_var.get()
        config["mute"] = mute_var.get()
        config["alarm_sound"] = alarm_sound_var.get()
    except Exception as e:
        print(f"同步 UI 参数异常: {e}")

def update_button_states():
    """统一同步大窗口和迷你窗口的按键可用状态"""
    if running:
        start_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)
        if mini_start_btn and mini_start_btn.winfo_exists():
            mini_start_btn.config(state=tk.DISABLED)
        if mini_stop_btn and mini_stop_btn.winfo_exists():
            mini_stop_btn.config(state=tk.NORMAL)
    else:
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)
        if mini_start_btn and mini_start_btn.winfo_exists():
            mini_start_btn.config(state=tk.NORMAL)
        if mini_stop_btn and mini_stop_btn.winfo_exists():
            mini_stop_btn.config(state=tk.DISABLED)

def start_loop():
    global running
    if not running:
        sync_ui_to_config()  # 启动时强制实时同步界面当前输入的值
        running = True
        append_log(f"--- 启动系统 (检测与控制间隔: {config['ocr_interval']} ms) ---")
        threading.Thread(target=control_loop, daemon=True).start()
        update_button_states()

def stop_loop():
    global running, alarm_triggered
    running = False
    stop_alarm()
    alarm_triggered = False
    append_log("--- 停止系统 ---")
    update_button_states()

def save_all_settings():
    try:
        sync_ui_to_config()
        save_config()
        append_log("系统设置参数已保存！")
        messagebox.showinfo("成功", "所有参数已成功保存！")
    except ValueError:
        messagebox.showerror("错误", "请输入有效的数值参数")

def restore_defaults():
    global config
    config = DEFAULT_CONFIG.copy()
    update_ui_from_config()
    save_config()
    append_log("恢复默认配置参数")
    messagebox.showinfo("恢复", "已恢复为默认参数")

def update_ui_from_config():
    entries_map = [
        (water_mid_entry, "water_mid"),
        (water_high_entry, "water_high"),
        (water_low_entry, "water_low"),
        (freq_high_entry, "freq_high"),
        (freq_low_entry, "freq_low"),
        (ocr_interval_entry, "ocr_interval"),
        (scale_entry, "ocr_scale"),
        (contrast_entry, "ocr_contrast"),
        (blur_entry, "ocr_blur"),
        (thresh_entry, "ocr_thresh"),
        (morph_entry, "ocr_morph")
    ]
    for entry, key in entries_map:
        entry.delete(0, tk.END)
        entry.insert(0, str(config.get(key, DEFAULT_CONFIG.get(key))))

    invert_var.set(config.get("ocr_invert", False))
    sharpen_var.set(config.get("ocr_sharpen", True))
    binarize_var.set(config.get("ocr_binarize", False))

    loop_var.set(config["loop_alarm"])
    mute_var.set(config["mute"])
    sound = config["alarm_sound"]
    alarm_sound_var.set(sound if sound in SOUND_LIST else SOUND_LIST[0])

    wr = config["water_rect"]
    water_rect_label.config(text=f"区域: {wr[0]},{wr[1]} {wr[2]}x{wr[3]}")
    fr = config["freq_rect"]
    freq_rect_label.config(text=f"区域: {fr[0]},{fr[1]} {fr[2]}x{fr[3]}")

    p1 = config["point1"]
    point1_label.config(text=f"坐标: {p1[0]},{p1[1]}")
    p2 = config["point2"]
    point2_label.config(text=f"坐标: {p2[0]},{p2[1]}")

# -------------------- 迷你小窗口逻辑 --------------------
def open_mini_window():
    global mini_win, mini_water_label, mini_freq_label, mini_status_label, mini_start_btn, mini_stop_btn

    if mini_win is not None and mini_win.winfo_exists():
        mini_win.deiconify()
        mini_win.lift()
        root.withdraw()
        return

    mini_win = tk.Toplevel(root)
    mini_win.title("迷你控制")
    mini_win.geometry("220x180")
    mini_win.attributes("-topmost", True)
    mini_win.resizable(False, False)

    def close_mini():
        mini_win.destroy()
        root.deiconify()

    mini_win.protocol("WM_DELETE_WINDOW", close_mini)

    # 监控数值简显
    info_frame = tk.Frame(mini_win, pady=6)
    info_frame.pack(fill=tk.X)

    mini_water_label = tk.Label(info_frame, text="液位: --", font=("Microsoft YaHei", 10, "bold"), fg="blue")
    mini_water_label.pack()

    mini_freq_label = tk.Label(info_frame, text="频率: --", font=("Microsoft YaHei", 10, "bold"), fg="blue")
    mini_freq_label.pack()

    mini_status_label = tk.Label(info_frame, text="状态: 正常", font=("Microsoft YaHei", 9), fg="green")
    mini_status_label.pack()

    # 启动/停止按钮行
    btn_frame1 = tk.Frame(mini_win, pady=3)
    btn_frame1.pack()

    mini_start_btn = tk.Button(btn_frame1, text="启动系统", command=start_loop, bg="#4CAF50", fg="white", width=8, font=("Microsoft YaHei", 9, "bold"))
    mini_start_btn.pack(side=tk.LEFT, padx=3)

    mini_stop_btn = tk.Button(btn_frame1, text="停止系统", command=stop_loop, bg="#F44336", fg="white", width=8, font=("Microsoft YaHei", 9, "bold"))
    mini_stop_btn.pack(side=tk.LEFT, padx=3)

    # 返回大窗口按钮
    btn_frame2 = tk.Frame(mini_win, pady=5)
    btn_frame2.pack()

    back_btn = tk.Button(btn_frame2, text="返回大窗口", command=close_mini, width=18, font=("Microsoft YaHei", 9))
    back_btn.pack()

    update_button_states()
    root.withdraw()  # 隐藏主大窗口

# -------------------- GUI 构建 --------------------
init_dirs()
load_config()

root = tk.Tk()
root.title("液位/水泵控制 V2.4 (小窗口与动态静音增强版)")
root.geometry("560x930")
root.resizable(True, True)

icon_path = get_resource_path("1.ico")
if os.path.exists(icon_path):
    try:
        root.iconbitmap(icon_path)
    except Exception:
        pass

tk.Label(root, text="水位水泵控制系统 V2.4", font=("Microsoft YaHei", 12, "bold")).pack(pady=3)

# 1. 预处理图像大图预览
ocr_frame = tk.LabelFrame(root, text="实时识别与预处理大图预览", padx=10, pady=4, fg="darkblue", font=("Microsoft YaHei", 9, "bold"))
ocr_frame.pack(fill=tk.X, padx=12, pady=3)

row_w = tk.Frame(ocr_frame)
row_w.pack(fill=tk.X, pady=2)
tk.Label(row_w, text="液位：", font=("Microsoft YaHei", 9, "bold")).pack(side=tk.LEFT)
water_label = tk.Label(row_w, text="--", fg="blue", font=("Microsoft YaHei", 9, "bold"))
water_label.pack(side=tk.LEFT, padx=5)
water_rect_label = tk.Label(row_w, text="区域: --", fg="gray", font=("Microsoft YaHei", 8))
water_rect_label.pack(side=tk.LEFT, padx=5)
tk.Button(row_w, text="框选液位", command=lambda: select_region_on_screen(update_water_rect)).pack(side=tk.RIGHT)

water_preview = tk.Label(ocr_frame, text="[液位预处理图像预览]", bg="#222222", fg="#888888", pady=12, relief="sunken", bd=2)
water_preview.pack(fill=tk.X, pady=3)

row_f = tk.Frame(ocr_frame)
row_f.pack(fill=tk.X, pady=2)
tk.Label(row_f, text="频率：", font=("Microsoft YaHei", 9, "bold")).pack(side=tk.LEFT)
freq_label = tk.Label(row_f, text="--", fg="blue", font=("Microsoft YaHei", 9, "bold"))
freq_label.pack(side=tk.LEFT, padx=5)
freq_rect_label = tk.Label(row_f, text="区域: --", fg="gray", font=("Microsoft YaHei", 8))
freq_rect_label.pack(side=tk.LEFT, padx=5)
tk.Button(row_f, text="框选频率", command=lambda: select_region_on_screen(update_freq_rect)).pack(side=tk.RIGHT)

freq_preview = tk.Label(ocr_frame, text="[频率预处理图像预览]", bg="#222222", fg="#888888", pady=12, relief="sunken", bd=2)
freq_preview.pack(fill=tk.X, pady=3)

row_s = tk.Frame(ocr_frame)
row_s.pack(fill=tk.X, pady=1)
tk.Label(row_s, text="系统状态：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
status_label = tk.Label(row_s, text="正常", fg="green", font=("Microsoft YaHei", 9, "bold"))
status_label.pack(side=tk.LEFT, padx=5)

# 2. 图像预处理参数
opt_frame = tk.LabelFrame(root, text="图像预处理调节 (解决识别失败/黑底/模糊)", padx=10, pady=4)
opt_frame.pack(fill=tk.X, padx=12, pady=3)

row_o1 = tk.Frame(opt_frame)
row_o1.pack(fill=tk.X, pady=1)

invert_var = tk.BooleanVar(value=False)
tk.Checkbutton(row_o1, text="颜色反色(黑底必开)", variable=invert_var, fg="red").pack(side=tk.LEFT, padx=2)

sharpen_var = tk.BooleanVar(value=True)
tk.Checkbutton(row_o1, text="边缘锐化(修复字模糊)", variable=sharpen_var, fg="darkgreen").pack(side=tk.LEFT, padx=6)

binarize_var = tk.BooleanVar(value=False)
tk.Checkbutton(row_o1, text="二值化", variable=binarize_var).pack(side=tk.LEFT, padx=2)

row_o2 = tk.Frame(opt_frame)
row_o2.pack(fill=tk.X, pady=2)

tk.Label(row_o2, text="放大倍数:", font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky="e")
scale_entry = tk.Entry(row_o2, width=5)
scale_entry.grid(row=0, column=1, padx=2)

tk.Label(row_o2, text="对比度:", font=("Microsoft YaHei", 9)).grid(row=0, column=2, sticky="e")
contrast_entry = tk.Entry(row_o2, width=5)
contrast_entry.grid(row=0, column=3, padx=2)

tk.Label(row_o2, text="降噪(0/3):", font=("Microsoft YaHei", 9)).grid(row=0, column=4, sticky="e")
blur_entry = tk.Entry(row_o2, width=5)
blur_entry.grid(row=0, column=5, padx=2)

row_o3 = tk.Frame(opt_frame)
row_o3.pack(fill=tk.X, pady=2)

tk.Label(row_o3, text="二值阈值(0自动):", font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky="e")
thresh_entry = tk.Entry(row_o3, width=5)
thresh_entry.grid(row=0, column=1, padx=2)

tk.Label(row_o3, text="笔画加粗/瘦身(-2~2):", font=("Microsoft YaHei", 9)).grid(row=0, column=2, sticky="e")
morph_entry = tk.Entry(row_o3, width=5)
morph_entry.grid(row=0, column=3, padx=2)

# 3. 参数设置
param_frame = tk.LabelFrame(root, text="控制与报警阈值设置", padx=10, pady=4)
param_frame.pack(fill=tk.X, padx=12, pady=3)

tk.Label(param_frame, text="液位中间值：", font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky="e", padx=2, pady=2)
water_mid_entry = tk.Entry(param_frame, width=9)
water_mid_entry.grid(row=0, column=1, sticky="w", padx=2, pady=2)

tk.Label(param_frame, text="液位上限(报警)：", font=("Microsoft YaHei", 9)).grid(row=1, column=0, sticky="e", padx=2, pady=2)
water_high_entry = tk.Entry(param_frame, width=9)
water_high_entry.grid(row=1, column=1, sticky="w", padx=2, pady=2)

tk.Label(param_frame, text="液位下限(报警)：", font=("Microsoft YaHei", 9)).grid(row=2, column=0, sticky="e", padx=2, pady=2)
water_low_entry = tk.Entry(param_frame, width=9)
water_low_entry.grid(row=2, column=1, sticky="w", padx=2, pady=2)

tk.Label(param_frame, text="频率上限(报警)：", font=("Microsoft YaHei", 9)).grid(row=0, column=2, sticky="e", padx=(15, 2), pady=2)
freq_high_entry = tk.Entry(param_frame, width=9)
freq_high_entry.grid(row=0, column=3, sticky="w", padx=2, pady=2)

tk.Label(param_frame, text="频率下限(报警)：", font=("Microsoft YaHei", 9)).grid(row=1, column=2, sticky="e", padx=(15, 2), pady=2)
freq_low_entry = tk.Entry(param_frame, width=9)
freq_low_entry.grid(row=1, column=3, sticky="w", padx=2, pady=2)

tk.Label(param_frame, text="检测间隔(ms)：", font=("Microsoft YaHei", 9)).grid(row=2, column=2, sticky="e", padx=(15, 2), pady=2)
ocr_interval_entry = tk.Entry(param_frame, width=9)
ocr_interval_entry.grid(row=2, column=3, sticky="w", padx=2, pady=2)

# 4. 报警与坐标
bottom_group = tk.Frame(root)
bottom_group.pack(fill=tk.X, padx=12, pady=2)

alarm_frame = tk.LabelFrame(bottom_group, text="报警设置", padx=6, pady=2)
alarm_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

row_a1 = tk.Frame(alarm_frame)
row_a1.pack(fill=tk.X, pady=1)
alarm_sound_var = tk.StringVar(value=SOUND_LIST[0])
sound_combo = ttk.Combobox(row_a1, textvariable=alarm_sound_var, values=SOUND_LIST, state="readonly", width=14)
sound_combo.pack(side=tk.LEFT, padx=2)
tk.Button(row_a1, text="试听", command=test_sound).pack(side=tk.LEFT, padx=2)

row_a2 = tk.Frame(alarm_frame)
row_a2.pack(fill=tk.X, pady=1)
loop_var = tk.BooleanVar(value=True)
tk.Checkbutton(row_a2, text="循环报警", variable=loop_var).pack(side=tk.LEFT)
mute_var = tk.BooleanVar(value=False)
# 绑定 command=on_mute_toggle 实现即时静音切断
tk.Checkbutton(row_a2, text="静音", variable=mute_var, command=on_mute_toggle).pack(side=tk.LEFT, padx=5)

coord_frame = tk.LabelFrame(bottom_group, text="控制坐标", padx=6, pady=2)
coord_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

row_c1 = tk.Frame(coord_frame)
row_c1.pack(fill=tk.X, pady=1)
tk.Button(row_c1, text="减频坐标(点1)", command=lambda: select_point_on_screen(update_point1)).pack(side=tk.LEFT)
point1_label = tk.Label(row_c1, text="坐标: --", fg="gray", font=("Microsoft YaHei", 8))
point1_label.pack(side=tk.LEFT, padx=4)

row_c2 = tk.Frame(coord_frame)
row_c2.pack(fill=tk.X, pady=1)
tk.Button(row_c2, text="加频坐标(点2)", command=lambda: select_point_on_screen(update_point2)).pack(side=tk.LEFT)
point2_label = tk.Label(row_c2, text="坐标: --", fg="gray", font=("Microsoft YaHei", 8))
point2_label.pack(side=tk.LEFT, padx=4)

# 5. 控制按钮
ctrl_frame = tk.Frame(root)
ctrl_frame.pack(fill=tk.X, padx=12, pady=4)

start_btn = tk.Button(ctrl_frame, text="启动系统", command=start_loop, width=8, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 9, "bold"))
start_btn.pack(side=tk.LEFT, padx=2)
stop_btn = tk.Button(ctrl_frame, text="停止系统", command=stop_loop, state=tk.DISABLED, width=8, bg="#F44336", fg="white", font=("Microsoft YaHei", 9, "bold"))
stop_btn.pack(side=tk.LEFT, padx=2)
tk.Button(ctrl_frame, text="切换小窗口", command=open_mini_window, width=9, bg="#2196F3", fg="white", font=("Microsoft YaHei", 9, "bold")).pack(side=tk.LEFT, padx=2)
tk.Button(ctrl_frame, text="保存设置", command=save_all_settings, width=8, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=2)
tk.Button(ctrl_frame, text="恢复默认", command=restore_defaults, width=8, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=2)

# 6. 运行诊断日志框
log_frame = tk.LabelFrame(root, text="运行诊断日志", padx=6, pady=4, fg="brown", font=("Microsoft YaHei", 9, "bold"))
log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(2, 8))

log_box = scrolledtext.ScrolledText(log_frame, height=8, font=("Consolas", 8), bg="#1E1E1E", fg="#00FF00")
log_box.pack(fill=tk.BOTH, expand=True)

update_ui_from_config()
append_log("系统准备就绪，点击【启动系统】开始监控。")

root.mainloop()
