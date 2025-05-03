#!/usr/bin/env python3
"""
Pi-Zero-2W hyperspectral node  ⟨760/770/780 nm⟩
Captures on GPIO-17 trigger, sends metadata & histogram over /dev/serial0.
"""

import os, time, json, struct, datetime, threading, sys
from gpiozero          import Button
from picamera2         import Picamera2
from PIL               import Image      # sudo apt install python3-pillow
import numpy           as np
import serial

# ────────── CONFIG ──────────────────────────────────────────────────────────
TRIGGER_PIN      = 17
FILTER_ID        = "760"                 # change on each Pi
SAVE_DIR         = "/home/pi/images"
SERIAL_DEV       = "/dev/serial0"
BAUD             = 115200
CHUNK            = 1024                  # bytes per payload block
ACK_TIMEOUT      = 10                    # s

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

    # --- histogram (monochrome) -------------------------------------------
    img     = Image.open(fpath).convert("L")          # 8-bit grey
    hist    = img.histogram()                        # 256 ints

    meta = {
        "type"     : "capture",
        "filter_id": FILTER_ID,
        "ts_utc"   : ts,
        "fname"    : fname,
        "w"        : img.width,
        "h"        : img.height,
        "hist"     : hist
    }
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
