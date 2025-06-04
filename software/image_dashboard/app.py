# app.py
from flask import Flask, render_template, redirect, request, url_for, send_from_directory
import os, subprocess, RPi.GPIO as GPIO, time
from config import REMOTE_PI_IPS

app = Flask(__name__)

# Setup GPIO pin 17
GPIO.setmode(GPIO.BCM)
CAPTURE_PIN = 17
GPIO.setup(CAPTURE_PIN, GPIO.OUT, initial=GPIO.HIGH)

IMAGE_DIR = os.path.expanduser("~/images")

@app.route('/')
def index():
    images = sorted(os.listdir(IMAGE_DIR))
    return render_template("index.html", images=images)

@app.route('/clear', methods=["POST"])
def clear_images():
    for f in os.listdir(IMAGE_DIR):
        os.remove(os.path.join(IMAGE_DIR, f))
    return redirect(url_for('index'))

@app.route('/shutdown', methods=["POST"])
def shutdown():
    for ip in REMOTE_PI_IPS:
        subprocess.Popen(["ssh", f"pi@{ip}", "sudo shutdown now"])
    return redirect(url_for('index'))

@app.route('/capture', methods=["POST"])
def capture():
    GPIO.output(CAPTURE_PIN, GPIO.LOW)
    time.sleep(0.1)
    GPIO.output(CAPTURE_PIN, GPIO.HIGH)
    return redirect(url_for('index'))

@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)

