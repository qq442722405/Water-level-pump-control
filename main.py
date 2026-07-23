import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import pygame
import datetime
from PIL import ImageGrab, Image, ImageTk
import pyautogui
from ocr import OcrReader

# -------------------- 全局配置 --------------------
CONFIG_FILE = "config.json"
LOG_DIR = "logs"
MODEL_DIR = "models"
ASSETS_DIR = "assets"

DEFAULT_CONFIG = {
    "water_high": 120,
    "water_low": 90,
    "freq_high": 50,
    "freq_low": 35,
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
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config.update(json.load(f))
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
    except:
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

def play_alarm(loop=True):
    if config["mute"]:
        return
    path = get_alarm_path(config["alarm_sound"])
    if not path:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
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
    except:
        pass

def test_sound():
    play_alarm(loop=False)

# -------------------- 屏幕区域 / 点选择 --------------------
def select_region_on_screen(callback, preview_widget=None):
    """
    全屏半透明窗口拖框选择区域，选择完后若 preview_widget 不为 None 则更新预览
    callback 接收 (x,y,w,h)
    """
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
        top.destroy()
        if w > 5 and h > 5:
            callback(x1, y1, w, h)
            if preview_widget:
                update_preview(preview_widget, (x1, y1, w, h))

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_move)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)

    def on_esc(event):
        top.destroy()
    top.bind("<Escape>", on_esc)
    top.focus_force()
    top.grab_set()

def select_point_on_screen(callback):
    top = tk.Toplevel(root)
    top.attributes("-fullscreen", True)
    top.attributes("-alpha", 0.01)
    top.attributes("-topmost", True)
    top.configure(bg='black')
    def on_click(event):
        top.destroy()
        callback(event.x_root, event.y_root)
    top.bind("<Button-1>", on_click)
    top.bind("<Escape>", lambda e: top.destroy())
    top.focus_force()
    top.grab_set()

def update_preview(label_widget, bbox):
    """截取指定区域并显示到 label_widget 上（缩放至 200x50 以内）"""
    try:
        img = ImageGrab.grab(bbox=bbox)
        img.thumbnail((200, 50))
        photo = ImageTk.PhotoImage(img)
        label_widget.configure(image=photo)
        label_widget.image = photo   # 保持引用
    except Exception as e:
        label_widget.configure(image='', text="预览失败")

# -------------------- UI 更新回调 --------------------
def update_water_rect(x, y, w, h):
    config["water_rect"] = [x, y, w, h]
    water_rect_label.config(text=f"区域: {x},{y} {w}x{h}")
    update_preview(water_preview, (x, y, w, h))
    save_config()

def update_freq_rect(x, y, w, h):
    config["freq_rect"] = [x, y, w, h]
    freq_rect_label.config(text=f"区域: {x},{y} {w}x{h}")
    update_preview(freq_preview, (x, y, w, h))
    save_config()

def update_point1(x, y):
    config["point1"] = [x, y]
    point1_label.config(text=f"坐标: {x},{y}")
    save_config()

def update_point2(x, y):
    config["point2"] = [x, y]
    point2_label.config(text=f"坐标: {x},{y}")
    save_config()

# -------------------- 控制循环 --------------------
def control_loop():
    global running, abnormal_count, last_water_value, alarm_triggered
    try:
        reader = OcrReader(config.get("easyocr_model", MODEL_DIR))
    except Exception as e:
        root.after(0, messagebox.showerror, "模型错误", f"无法加载 OCR 模型: {e}")
        stop_loop()
        return

    while running:
        wr = config["water_rect"]
        fr = config["freq_rect"]
        try:
            water_img = ImageGrab.grab(bbox=(wr[0], wr[1], wr[0]+wr[2], wr[1]+wr[3]))
            freq_img = ImageGrab.grab(bbox=(fr[0], fr[1], fr[0]+fr[2], fr[1]+fr[3]))
        except Exception as e:
            log(f"截图失败: {e}")
            time.sleep(config["ocr_interval"]/1000)
            continue

        water_val = reader.read_number(water_img)
        freq_val = reader.read_number(freq_img)

        root.after(0, update_display, water_val, freq_val)

        if water_val is None or freq_val is None:
            time.sleep(config["ocr_interval"]/1000)
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
            time.sleep(config["adjust_delay"]/1000)
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

        time.sleep(config["ocr_interval"]/1000)

def update_display(water, freq):
    if water is not None:
        water_label.config(text=f"{water:.1f}")
    else:
        water_label.config(text="识别失败")
    if freq is not None:
        freq_label.config(text=f"{freq:.1f}")   # 不再显示 Hz
    else:
        freq_label.config(text="识别失败")
    status_label.config(text="报警中" if alarm_triggered else "正常",
                        foreground="red" if alarm_triggered else "green")
    count_label.config(text=str(abnormal_count))

def trigger_alarm():
    play_alarm(loop=config["loop_alarm"])
    take_screenshot()
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast("液位控制报警", "连续异常次数达到设定值！", duration=5)
    except:
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
    water_high_entry.delete(0, tk.END); water_high_entry.insert(0, str(config["water_high"]))
    water_low_entry.delete(0, tk.END); water_low_entry.insert(0, str(config["water_low"]))
    freq_high_entry.delete(0, tk.END); freq_high_entry.insert(0, str(config["freq_high"]))
    freq_low_entry.delete(0, tk.END); freq_low_entry.insert(0, str(config["freq_low"]))
    ocr_interval_entry.delete(0, tk.END); ocr_interval_entry.insert(0, str(config["ocr_interval"]))
    adjust_delay_entry.delete(0, tk.END); adjust_delay_entry.insert(0, str(config["adjust_delay"]))
    alarm_count_entry.delete(0, tk.END); alarm_count_entry.insert(0, str(config["alarm_count"]))
    loop_var.set(config["loop_alarm"])
    mute_var.set(config["mute"])
    sound = config["alarm_sound"]
    if sound in SOUND_LIST:
        alarm_sound_var.set(sound)
    else:
        alarm_sound_var.set(SOUND_LIST[0])
    wr = config["water_rect"]
    water_rect_label.config(text=f"区域: {wr[0]},{wr[1]} {wr[2]}x{wr[3]}")
    update_preview(water_preview, (wr[0], wr[1], wr[2], wr[3]))
    fr = config["freq_rect"]
    freq_rect_label.config(text=f"区域: {fr[0]},{fr[1]} {fr[2]}x{fr[3]}")
    update_preview(freq_preview, (fr[0], fr[1], fr[2], fr[3]))
    p1 = config["point1"]
    point1_label.config(text=f"坐标: {p1[0]},{p1[1]}")
    p2 = config["point2"]
    point2_label.config(text=f"坐标: {p2[0]},{p2[1]}")

# -------------------- 构建 GUI --------------------
root = tk.Tk()
root.title("水位水泵控制 V2.0")
root.geometry("440x680")   # 加高窗口
root.resizable(False, False)

try:
    root.iconbitmap("1.ico")
except:
    pass

load_config()
init_dirs()

# ========== 标题 ==========
tk.Label(root, text="水位水泵控制 V2.0", font=("Arial", 14, "bold")).pack(pady=5)

# ========== 实时 OCR + 预览 ==========
ocr_frame = tk.LabelFrame(root, text="实时 OCR & 预览", padx=5, pady=5)
ocr_frame.pack(fill=tk.X, padx=10, pady=5)

# 液位行
row_w = tk.Frame(ocr_frame)
row_w.pack(fill=tk.X, pady=2)
tk.Label(row_w, text="液位：").pack(side=tk.LEFT)
water_label = tk.Label(row_w, text="--", fg="blue", font=("Arial", 12))
water_label.pack(side=tk.LEFT, padx=5)
water_rect_label = tk.Label(row_w, text="区域: 100,100 120x35", fg="gray")
water_rect_label.pack(side=tk.LEFT, padx=5)
tk.Button(row_w, text="选择区域", command=lambda: select_region_on_screen(update_water_rect, water_preview)).pack(side=tk.RIGHT, padx=2)

# 液位预览
water_preview = tk.Label(ocr_frame, text="液位预览", bg="lightgray", width=200, height=30)
water_preview.pack(pady=2)

# 频率行
row_f = tk.Frame(ocr_frame)
row_f.pack(fill=tk.X, pady=2)
tk.Label(row_f, text="频率：").pack(side=tk.LEFT)
freq_label = tk.Label(row_f, text="--", fg="blue", font=("Arial", 12))
freq_label.pack(side=tk.LEFT, padx=5)
freq_rect_label = tk.Label(row_f, text="区域: 350,100 120x35", fg="gray")
freq_rect_label.pack(side=tk.LEFT, padx=5)
tk.Button(row_f, text="选择区域", command=lambda: select_region_on_screen(update_freq_rect, freq_preview)).pack(side=tk.RIGHT, padx=2)

# 频率预览
freq_preview = tk.Label(ocr_frame, text="频率预览", bg="lightgray", width=200, height=30)
freq_preview.pack(pady=2)

# 状态行
row_s = tk.Frame(ocr_frame)
row_s.pack(fill=tk.X, pady=2)
tk.Label(row_s, text="状态：").pack(side=tk.LEFT)
status_label = tk.Label(row_s, text="正常", fg="green")
status_label.pack(side=tk.LEFT, padx=5)
tk.Label(row_s, text="连续异常：").pack(side=tk.LEFT, padx=(20,0))
count_label = tk.Label(row_s, text="0", fg="red")
count_label.pack(side=tk.LEFT)

# ========== 参数设置 ==========
param_frame = tk.LabelFrame(root, text="参数设置", padx=5, pady=5)
param_frame.pack(fill=tk.X, padx=10, pady=5)

def add_param_row(label, var_name, unit=""):
    row = tk.Frame(param_frame)
    row.pack(fill=tk.X, pady=2)
    tk.Label(row, text=label, width=14, anchor="e").pack(side=tk.LEFT)
    entry = tk.Entry(row, width=8)
    entry.pack(side=tk.LEFT, padx=5)
    if unit:
        tk.Label(row, text=unit).pack(side=tk.LEFT)
    return entry

water_high_entry = add_param_row("液位上限：")
water_low_entry = add_param_row("液位下限：")
freq_high_entry = add_param_row("频率上限：")
freq_low_entry = add_param_row("频率下限：")
ocr_interval_entry = add_param_row("检测间隔(ms)：")
adjust_delay_entry = add_param_row("调整等待(ms)：")
alarm_count_entry = add_param_row("报警次数：")

# ========== 报警设置 ==========
alarm_frame = tk.LabelFrame(root, text="报警设置", padx=5, pady=5)
alarm_frame.pack(fill=tk.X, padx=10, pady=5)

row_a1 = tk.Frame(alarm_frame)
row_a1.pack(fill=tk.X, pady=2)
tk.Label(row_a1, text="声音：").pack(side=tk.LEFT)
alarm_sound_var = tk.StringVar(value=SOUND_LIST[0])
sound_combo = ttk.Combobox(row_a1, textvariable=alarm_sound_var, values=SOUND_LIST, state="readonly", width=22)
sound_combo.pack(side=tk.LEFT, padx=5)
tk.Button(row_a1, text="试听", command=test_sound).pack(side=tk.LEFT, padx=5)

row_a2 = tk.Frame(alarm_frame)
row_a2.pack(fill=tk.X, pady=2)
loop_var = tk.BooleanVar(value=True)
tk.Checkbutton(row_a2, text="循环报警", variable=loop_var).pack(side=tk.LEFT, padx=5)
mute_var = tk.BooleanVar(value=False)
tk.Checkbutton(row_a2, text="静音", variable=mute_var).pack(side=tk.LEFT, padx=20)

# ========== 操作坐标 ==========
coord_frame = tk.LabelFrame(root, text="操作坐标", padx=5, pady=5)
coord_frame.pack(fill=tk.X, padx=10, pady=5)

row_c1 = tk.Frame(coord_frame)
row_c1.pack(fill=tk.X, pady=2)
tk.Button(row_c1, text="选择减频坐标", command=lambda: select_point_on_screen(update_point1)).pack(side=tk.LEFT, padx=5)
point1_label = tk.Label(row_c1, text="坐标: 1250,560", fg="gray")
point1_label.pack(side=tk.LEFT, padx=10)

row_c2 = tk.Frame(coord_frame)
row_c2.pack(fill=tk.X, pady=2)
tk.Button(row_c2, text="选择加频坐标", command=lambda: select_point_on_screen(update_point2)).pack(side=tk.LEFT, padx=5)
point2_label = tk.Label(row_c2, text="坐标: 1320,560", fg="gray")
point2_label.pack(side=tk.LEFT, padx=10)

# ========== 控制按钮 ==========
ctrl_frame = tk.Frame(root)
ctrl_frame.pack(fill=tk.X, padx=10, pady=10)

start_btn = tk.Button(ctrl_frame, text="启动", command=start_loop, width=8, bg="lightgreen")
start_btn.pack(side=tk.LEFT, padx=5)
stop_btn = tk.Button(ctrl_frame, text="停止", command=stop_loop, state=tk.DISABLED, width=8, bg="lightcoral")
stop_btn.pack(side=tk.LEFT, padx=5)
tk.Button(ctrl_frame, text="保存设置", command=save_all_settings, width=10).pack(side=tk.LEFT, padx=5)
tk.Button(ctrl_frame, text="恢复默认", command=restore_defaults, width=10).pack(side=tk.LEFT, padx=5)

# 应用当前配置
update_ui_from_config()

root.mainloop()
