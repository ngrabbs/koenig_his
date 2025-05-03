from flask import Flask, request, jsonify, send_from_directory
import os, base64, uuid, json

app = Flask(__name__)
os.makedirs("images", exist_ok=True)          # where JPEGs will live

# Mock command queue
commands = {
    "commands": [
#	{"action": "reboot"}
#	{"action": "sleep", "value":"10"}
#        {"action": "set_interval", "value": 60},   # Initial command to change telemetry interval
#        {"action": "take_gps_snapshot"}            # Example of other commands
    ]
}


# Telemetry POST endpoint
@app.route('/telemetry', methods=['POST'])
def receive_telemetry():
    data = request.json
    print(f"Received telemetry: {data}")
    return jsonify({"status": "ok"})

@app.route("/acknowledge", methods=["POST"])
def acknowledge():
    data   = request.get_json(force=True, silent=True) or {}
    acked  = set(data.get("acknowledged", []))          # set of ids

    commands["commands"] = [
        c for c in commands["commands"] if c.get("id") not in acked
    ]
    return jsonify(status="commands cleared", remaining=len(commands["commands"]))

# Commands GET endpoint
@app.route('/commands', methods=['GET'])
def send_commands():
    return jsonify(commands)

@app.route('/add_command', methods=['POST'])
def add_command():
    global commands
    new_cmd = request.json
    print(f"Adding command: {new_cmd}")

    # Add to the command queue
    commands["commands"].append(new_cmd)
    return jsonify({"status": "command added", "queue": commands["commands"]})

# --------------------------------------------------------------------------
# Existing queues and /telemetry, /commands, /acknowledge stay as-is
# --------------------------------------------------------------------------

# 1️⃣ metadata + histogram from each Pi
@app.route("/pi_meta", methods=["POST"])
def pi_meta():
    data = request.get_json(force=True, silent=True) or {}
    print("[PI-META]", json.dumps(data)[:200], "…")   # first 200 chars
    # TODO: store in a DB or CSV if you like
    return jsonify(status="meta stored")

# 2️⃣ raw JPEG upload (single-shot, no chunks here)
#    ESP32 adds header  X-Filename: <original_name.jpg>
@app.route("/upload_image", methods=["POST"])
def upload_image():
    fname = request.headers.get("X-Filename") or f"{uuid.uuid4()}.jpg"
    path  = os.path.join("images", os.path.basename(fname))
    with open(path, "wb") as f:
        f.write(request.data)
    print(f"[IMAGE] saved → {path}  ({len(request.data):,} bytes)")
    return jsonify(status="stored", file=fname)

# Optional helper to download an image later
@app.route("/images/<path:fname>")
def get_image(fname):
    return send_from_directory("images", fname)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
