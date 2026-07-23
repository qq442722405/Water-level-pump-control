import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import threading
import time
import json
import os
import pyautogui
import pygame
import datetime
from PIL import ImageGrab
from ocr import OcrReader

# -------------------- 配置 --------------------
CONFIG_FILE = "config.json"
LOG_DIR = "logs"
ALARM_SOUND = "alarm.wav"

default_config = {
    "water_high": 120,
    "water_low": 90,
    "freq_high": 50,
    "freq_low": 35,
    "alarm_count": 5,
    "ocr_interval": 500,
    "click_delay": 300,
    "point1": [1250, 560],
    "point2": [1320, 560],
    "water_rect": [100, 100, 120, 35],
    "freq_rect": [350, 100, 120, 35],
    "easyocr_model": "models"
}

config = default_config.copy()
running = False
alarm_triggered = False
abnormal_count = 0
last_water_value = None

# -------------------- 工具函数 --------------------
def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            saved = json.load(f)
            config.update(saved)
    else:
        save_config()

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def init_log():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(LOG_DIR, "events.log"), "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

def take_screenshot():
    filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_alarm.png"
    path = os.path.join(LOG_DIR, filename)
    ImageGrab.grab().save(path)
    log(f"截图已保存: {path}")

def play_alarm():
    try:
        pygame.mixer.init()
        if os.path.exists(ALARM_SOUND):
            pygame.mixer.music.load(ALARM_SOUND)
            pygame.mixer.music.play(-1)  # 循环播放
    except Exception as e:
        print(f"播放报警失败: {e}")

def stop_alarm():
    try:
        pygame.mixer.music.stop()
    except:
        pass

# -------------------- 区域/点选择（简化版，使用对话框输入）--------------------
def select_region():
    x = simpledialog.askinteger("框选区域", "左上角 X:")
    y = simpledialog.askinteger("框选区域", "左上角 Y:")
    w = simpledialog.askinteger("框选区域", "宽度:")
    h = simpledialog.askinteger("框选区域", "高度:")
    if None not in (x, y, w, h):
        return [x, y, w, h]
    return None

def select_point():
    x = simpledialog.askinteger("选择点击位置", "X 坐标:")
    y = simpledialog.askinteger("选择点击位置", "Y 坐标:")
    if None not in (x, y):
        return [x, y]
    return None

def re_select():
    messagebox.showinfo("提示", "请框选液位数字区域")
    wr = select_region()
    if wr: config["water_rect"] = wr

    messagebox.showinfo("提示", "请框选频率数字区域")
    fr = select_region()
    if fr: config["freq_rect"] = fr

    messagebox.showinfo("提示", "选择点击位置1（减频）")
    p1 = select_point()
    if p1: config["point1"] = p1

    messagebox.showinfo("提示", "选择点击位置2（加频）")
    p2 = select_point()
    if p2: config["point2"] = p2

    save_config()
    messagebox.showinfo("完成", "框选配置已保存！")

# -------------------- 控制循环 --------------------
def control_loop():
    global running, abnormal_count, last_water_value, alarm_triggered
    try:
        reader = OcrReader(config["easyocr_model"])
    except Exception as e:
        root.after(0, messagebox.showerror, "模型错误", f"无法加载 OCR 模型: {e}")
        stop_loop()
        return

    while running:
        # 截取区域
        water_bbox = (
            config["water_rect"][0],
            config["water_rect"][1],
            config["water_rect"][0] + config["water_rect"][2],
            config["water_rect"][1] + config["water_rect"][3]
        )
        freq_bbox = (
            config["freq_rect"][0],
            config["freq_rect"][1],
            config["freq_rect"][0] + config["freq_rect"][2],
            config["freq_rect"][1] + config["freq_rect"][3]
        )

        water_img = ImageGrab.grab(bbox=water_bbox)
        freq_img = ImageGrab.grab(bbox=freq_bbox)

        water_val = reader.read_number(water_img)
        freq_val = reader.read_number(freq_img)

        root.after(0, update_display, water_val, freq_val)

        if water_val is None or freq_val is None:
            time.sleep(config["ocr_interval"] / 1000)
            continue

        clicked = False
        if water_val > config["water_high"]:
            if freq_val < config["freq_high"]:
                pyautogui.click(config["point1"][0], config["point1"][1])
                log(f"液位 {water_val:.1f}>{config['water_high']}，频率{freq_val:.1f}<上限，点击位置1")
                clicked = True
                time.sleep(config["click_delay"] / 1000)
            else:
                log(f"液位超标但频率已达上限{freq_val:.1f}，不操作")
        elif water_val < config["water_low"]:
            if freq_val > config["freq_low"]:
                pyautogui.click(config["point2"][0], config["point2"][1])
                log(f"液位 {water_val:.1f}<{config['water_low']}，频率{freq_val:.1f}>下限，点击位置2")
                clicked = True
                time.sleep(config["click_delay"] / 1000)
            else:
                log(f"液位过低但频率已达下限{freq_val:.1f}，不操作")

        # 连续异常计数
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
            log(f"连续异常次数达{abnormal_count}，触发报警")
            root.after(0, trigger_alarm)
            alarm_triggered = True

        time.sleep(config["ocr_interval"] / 1000)

def update_display(water, freq):
    if water is not None:
        water_label.config(text=f"{water:.1f}")
    else:
        water_label.config(text="识别失败")
    if freq is not None:
        freq_label.config(text=f"{freq:.1f} Hz")
    else:
        freq_label.config(text="识别失败")
    status_label.config(text="报警中" if alarm_triggered else "正常", fg="red" if alarm_triggered else "green")
    count_label.config(text=str(abnormal_count))

def trigger_alarm():
    play_alarm()
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

def save_settings(vars):
    try:
        config["water_high"] = float(vars["water_high"].get())
        config["water_low"] = float(vars["water_low"].get())
        config["freq_high"] = float(vars["freq_high"].get())
        config["freq_low"] = float(vars["freq_low"].get())
        config["alarm_count"] = int(vars["alarm_count"].get())
        save_config()
        messagebox.showinfo("成功", "设置已保存")
    except ValueError:
        messagebox.showerror("错误", "请输入有效数字")

def choose_model_dir():
    path = filedialog.askdirectory(title="选择 EasyOCR 模型目录")
    if path:
        config["easyocr_model"] = path
        save_config()
        messagebox.showinfo("完成", "模型路径已更新")

# -------------------- GUI --------------------
root = tk.Tk()
root.title("液位自动控制")
root.geometry("360x450")
root.resizable(False, False)

load_config()
init_log()

# 显示区
tk.Label(root, text="液位OCR：").grid(row=0, column=0, sticky="e", pady=2)
water_label = tk.Label(root, text="--", fg="blue", font=("Arial", 12))
water_label.grid(row=0, column=1, sticky="w")

tk.Label(root, text="频率OCR：").grid(row=1, column=0, sticky="e", pady=2)
freq_label = tk.Label(root, text="--", fg="blue", font=("Arial", 12))
freq_label.grid(row=1, column=1, sticky="w")

tk.Label(root, text="当前状态：").grid(row=2, column=0, sticky="e", pady=2)
status_label = tk.Label(root, text="正常", fg="green", font=("Arial", 12))
status_label.grid(row=2, column=1, sticky="w")

tk.Label(root, text="-"*40).grid(row=3, columnspan=2)

params = [
    ("液位上限：", "water_high"),
    ("液位下限：", "water_low"),
    ("频率下限：", "freq_low"),
    ("频率上限：", "freq_high"),
    ("连续异常次数：", "alarm_count"),
]
entries = {}
for i, (label, key) in enumerate(params):
    tk.Label(root, text=label).grid(row=4+i, column=0, sticky="e")
    var = tk.StringVar(value=str(config[key]))
    ent = tk.Entry(root, textvariable=var, width=10)
    ent.grid(row=4+i, column=1, sticky="w")
    entries[key] = var

tk.Label(root, text="当前：").grid(row=9, column=0, sticky="e")
count_label = tk.Label(root, text="0", fg="red")
count_label.grid(row=9, column=1, sticky="w")

tk.Label(root, text="-"*40).grid(row=10, columnspan=2)

start_btn = tk.Button(root, text="启动", command=start_loop, width=10)
start_btn.grid(row=11, column=0, padx=5, pady=5)

stop_btn = tk.Button(root, text="停止", command=stop_loop, state=tk.DISABLED, width=10)
stop_btn.grid(row=11, column=1, padx=5, pady=5)

re_btn = tk.Button(root, text="重新框选", command=re_select, width=10)
re_btn.grid(row=12, column=0, padx=5, pady=5)

save_btn = tk.Button(root, text="保存设置", command=lambda: save_settings(entries), width=10)
save_btn.grid(row=12, column=1, padx=5, pady=5)

model_btn = tk.Button(root, text="选择模型路径", command=choose_model_dir)
model_btn.grid(row=13, column=0, columnspan=2, pady=10)

root.mainloop()