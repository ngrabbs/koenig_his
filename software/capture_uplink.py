#!/usr/bin/env python3
"""
Pi-Zero-2W hyperspectral node  ⟨760/770/780 nm⟩
Captures on GPIO-17 trigger, sends metadata & histogram over /dev/serial0.
"""

import os, subprocess, shlex, argparse, time, json, struct, datetime, threading, sys
from gpiozero          import Button
from picamera2         import Picamera2
from PIL               import Image      # sudo apt install python3-pillow
import numpy           as np
import serial

parser = argparse.ArgumentParser()
parser.add_argument("--dev", action="store_true",
                    help="Enable dev mode: scp image to ESP32 host")
args, _ = parser.parse_known_args()
# ────────── CONFIG ──────────────────────────────────────────────────────────
TRIGGER_PIN      = 17
FILTER_ID        = "760"                 # change on each Pi
SAVE_DIR         = "/home/pi/images"
SERIAL_DEV       = "/dev/serial0"
BAUD             = 115200
CHUNK            = 1024                  # bytes per payload block
ACK_TIMEOUT      = 10                    # s

# ────────── DEV CONFIG ──────────────────────────────────────────────────────
DEV_MODE   = args.dev or os.getenv("DEV_SCP") == "1"
ESP_HOST   = "192.168.4.1"          # mDNS or IP of flight‑controller
ESP_PATH   = "~/images"             # remote dir
ESP_USER   = "pi"                   # userid
SCP_CMD    = f"scp {{src}} {ESP_USER}@{ESP_HOST}:{ESP_PATH}/"
# ────────── SERIAL ──────────────────────────────────────────────────────────
ser = serial.Serial(SERIAL_DEV, BAUD, timeout=1)

def send_json(obj):
    line = json.dumps(obj, separators=(",", ":")) + "\n"
    ser.write(line.encode())

def wait_for(keyword, timeout):
    deadline = time.time() + timeout
    buff = b""
    while time.time() < deadline:
        buff += ser.read(32)
        if keyword.encode() in buff:
            return True
    return False

def stream_file(path):
    with open(path, "rb") as f:
        while (chunk := f.read(CHUNK)):
            chk   = 0
            for b in chunk: chk ^= b
            header = struct.pack("<H", len(chunk))  # 2-byte little-endian len
            ser.write(header + chunk + bytes([chk]))
    ser.write(b"\x00\x00")                # len==0 marks EOF

# ────────── SCP DEV MODE ────────────────────────────────────────────────────
# ensure we don’t block capture thread
def scp_async(local_path):
    if not DEV_MODE:
        return
    cmd = SCP_CMD.format(src=shlex.quote(local_path))
    subprocess.Popen(cmd, shell=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

# ────────── CAMERA ──────────────────────────────────────────────────────────
picam2  = Picamera2()
controls = dict(ExposureTime=500, AnalogueGain=1.0,
                ColourGains=(0.0,0.0), Saturation=0.0,
                AeEnable=0)
config   = picam2.create_still_configuration(controls=controls)
picam2.configure(config)
picam2.start()

# ────────── CAPTURE LOGIC ───────────────────────────────────────────────────
def capture_and_send():
    ts      = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname   = f"image_{FILTER_ID}_{ts}.jpg"
    fpath   = os.path.join(SAVE_DIR, fname)

    print(f"[{FILTER_ID}] Trigger → {fname}")
    picam2.capture_file(fpath)
    if DEV_MODE:
        scp_async(fpath)            # << uploads in background

    # --- histogram (monochrome) -------------------------------------------
    # .convert("L") throws away all color information, this makes the image
    # luminance only.  All three channels are collapsed using:
    # ITU-Rec-601 weighting
    img     = Image.open(fpath).convert("L")          # 8-bit grey
    hist    = img.histogram()                        # 256 ints

    # histogram for .convert("RGB")
    # three channels split
    img     = Image.open(fpath).convert("RGB")
    arr = np.array(img)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    hist_r  = np.bincount(r.flatten(), minlength=256).tolist()
    hist_g  = np.bincount(g.flatten(), minlength=256).tolist()
    hist_b  = np.bincount(b.flatten(), minlength=256).tolist()

    meta = {
        "type"     : "capture",
        "filter_id": FILTER_ID,
        "ts_utc"   : ts,
        "fname"    : fname,
        "w"        : img.width,
        "h"        : img.height,
        "hist" : {
            "luminance" : hist,          # the old grey histogram
            "r"         : hist_r,
            "g"         : hist_g,
            "b"         : hist_b
        }
    }
    if DEV_MODE:
        meta_path = os.path.splitext(fpath)[0] + ".json"
        # 1. write JSON metadata to disk
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
            # 2. scp metadata to webserver
            scp_async(meta_path)

    send_json(meta)                                  # step #2 & #3
    print("  meta+histogram sent, waiting for SEND_IMG…")

    # --- maybe TX the raw JPEG --------------------------------------------
    if wait_for("SEND_IMG", ACK_TIMEOUT):
        print("  streaming JPEG…")
        stream_file(fpath)
        print("  done.")
    else:
        print("  no image requested.")

# ────────── MAIN ────────────────────────────────────────────────────────────
os.makedirs(SAVE_DIR, exist_ok=True)
button = Button(TRIGGER_PIN, pull_up=True, bounce_time=0.05)
button.when_pressed = lambda: threading.Thread(target=capture_and_send,
                                               daemon=True).start()

print(f"[{FILTER_ID}] ready. Listening on GPIO{TRIGGER_PIN}…")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    picam2.stop()
