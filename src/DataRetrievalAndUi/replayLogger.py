import json
import socket
import time
import sys
import os
import math

# --- Triangulation function (identical to getAnchorData.py) ---
def triangulate_position(anchor1, anchor2, angle1_deg, angle2_deg):
    """
    AoA convention: 0° = up (+Y), 90° = right (+X), 180° = down, 270° = left.
    """
    angle1 = math.radians(angle1_deg)
    angle2 = math.radians(angle2_deg)
    x1, y1 = anchor1
    x2, y2 = anchor2

    # Use sin for dx, cos for dy so 0° is up (+Y)
    dx1 = math.sin(angle1)
    dy1 = math.cos(angle1)
    dx2 = math.sin(angle2)
    dy2 = math.cos(angle2)

    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) < 1e-6:
        x = (x1 + x2) / 2
        y = (y1 + y2) / 2
    else:
        t1 = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / denominator
        x = x1 + t1 * dx1
        y = y1 + t1 * dy1

    print(f"DEBUG: anchor1={anchor1}, anchor2={anchor2}, angle1={angle1_deg}, angle2={angle2_deg}, tag=({x:.2f}, {y:.2f})")
    return [x, y]

if len(sys.argv) > 1:
    LOGFILE = sys.argv[1]
else:
    LOGFILE = "tag_log.jsonl"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12346  # Match the port in your UI

def connect_with_retry():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for _ in range(10):
        try:
            sock.connect((SERVER_HOST, SERVER_PORT))
            return sock
        except ConnectionRefusedError:
            print("Server not ready, retrying...")
            time.sleep(1)
    raise Exception("Could not connect to UI after retries.")

def main():
    sock = connect_with_retry()
    print(f"Connected to UI at {SERVER_HOST}:{SERVER_PORT}")
    while True:  # Loop forever
        with open(LOGFILE, "r") as f:
            for line in f:
                entry = json.loads(line)
                raw = entry["raw_sensor_data"]
                anchor1, anchor2 = raw["anchors"]
                angle1, angle2 = raw["angles"]
                sensor_values = raw["sensor_values"]

                # Recompute tag position using current code!
                tag_position = triangulate_position(anchor1, anchor2, angle1, angle2)

                # Compose message for UI
                message = json.dumps({
                    "point": {"position": tag_position, "Uncertainty": 0},
                    "sensor_values": sensor_values
                })
                sock.sendall(message.encode("utf-8"))
                time.sleep(0.05)  # Adjust replay speed as needed

if __name__ == "__main__":
    main()