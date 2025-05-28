import json
import math
import os
import signal
import sys
import serial
import re
import time
import threading
import socket
from datetime import datetime
import json

def log_data(raw_sensor_data, logfile):
    # Save only the raw sensor data and timestamp
    with open(logfile, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "raw_sensor_data": raw_sensor_data
        }) + "\n")

# Set the server address and port
port= 12346
clients = set()
sensors=None

def init_serials():
    global sensors
    for i in range(len(sensors)):
        print(f"Open Sensor {i}:{sensors[i]['serial_port']} ")
        sensors[i]['serial']= serial.Serial(sensors[i]["serial_port"], 115200, timeout=0.05, rtscts=1)
        try:
            sensors[i]['serial'].isOpen()
            print(f"anchor{i} (first anchor) is opened!")
        except IOError:
            sensors[i]['serial'].close()
            sensors[i]['serial'].open()
            print("port was already open, was closed and opened again!")

risk_speed = None

def calculate_speed_along_line(current_angles, previous_angles, distance_between_antennas, last_time):
    if previous_angles is None:
        return 0, current_angles, time.time()
    current_time = time.time()
    time_difference = current_time - last_time
    delta_angle_1 = math.radians(current_angles[0]['val'] - previous_angles[0]['val'])
    delta_angle_2 = math.radians(current_angles[1]['val'] - previous_angles[1]['val'])
    parallel_distance_change = abs(distance_between_antennas * (delta_angle_1 - delta_angle_2) / 2)
    speed_along_line = parallel_distance_change / time_difference if time_difference > 0 else 0
    return speed_along_line, current_angles, current_time

def calculate_risk_level(speed_along_line, angle_antenna_1, angle_antenna_2):
    if ((angle_antenna_1 < 67 and angle_antenna_1 > 45) and (angle_antenna_2 < 22 and angle_antenna_2 >=0)) or ((angle_antenna_1 < 45 and angle_antenna_1 > 22) and angle_antenna_2 < 45) or (angle_antenna_1 < 22 and angle_antenna_2 < 45):
        risk_position = 1
    elif angle_antenna_1 > 67 or ((angle_antenna_1 < 67 and angle_antenna_1 > 45) and (angle_antenna_2 < 67 and angle_antenna_2 > 22)):
        risk_position = 2
    elif ((angle_antenna_1 < 67 and angle_antenna_1 > 45) and (angle_antenna_2 > 67)) or ((angle_antenna_1 < 45 and angle_antenna_1 > 22) and (angle_antenna_2 > 45)) or (angle_antenna_1 < 22 and angle_antenna_2 > 45):
        risk_position = 3
    else:
        risk_position = 1

    if speed_along_line > 0 and speed_along_line < 1:
        risk_speed = 2
    elif speed_along_line >= 1:
        risk_speed = 3
    else:
        risk_speed = 1

    if risk_speed == 3 or risk_position == 3:
        risk = 3
    elif risk_speed == 2 or risk_position == 2:
        risk = 2
    else:
        risk = 1

    return risk

def getanchor(sensor):
    if sensor['serial'].in_waiting > 0:
        dataStream_anchor = str(sensor['serial'].read(80))
        regex_anchor = re.split("UUDF:", dataStream_anchor)
        for listing in regex_anchor:
            if sensor['id'] in listing:
                parts = listing.split(",")
                if len(parts) == 9:
                    val=-int(parts[2])
                    sensor['val'].append(val)
        sensor['serial'].reset_input_buffer()

def on_close():
    for s in sensors:
        s['serial'].close()
    exit()

def getValues(results):
    global sensors
    numSensors=len(sensors)
    changed=False
    results=[]
    for i in range(numSensors):
        results.append(None)
        sensors[i]['val']=[]
        sensors[i]['thread'] = threading.Thread(target=getanchor, args=(sensors[i],))
        sensors[i]['thread'].start()
    for i in range(numSensors):
        sensors[i]['thread'].join()
    for i in range(numSensors):
        try:
            sensors[i]['result'] = sensors[i]['val'][0]
            changed=True
        except IndexError:
            None
    if changed:
        for i in range(numSensors):
            results[i]={"theta":sensors[i]['theta'],"val":sensors[i]['result'],"pos":sensors[i]['pos']}
        return results
    else: 
        return 0

server_running = True
server_socket = None
client_sockets = []
num_pack=0

def handle_client(client_socket, client_address):
    print(f"Connection from {client_address}")
    while server_running:
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            print(f"Received from {client_address}: {data.decode('utf-8')}")
        except Exception as e:
            print(f"Error receiving data from {client_address}: {e}")
            break
    print(f"Client {client_address} disconnected")
    client_sockets.remove(client_socket)
    client_socket.close()

def send_data_to_all_clients(data):
    global num_pack
    num_pack=num_pack+1
    spinner_chars = ['/', '|', '\\', '-']
    # For logging, print the sensor values
    try:
        datastruct=json.loads(data)
        if isinstance(datastruct, dict) and "sensor_values" in datastruct:
            print(f"\rSending to {len(client_sockets)} clients[{num_pack}]{spinner_chars[num_pack % len(spinner_chars)]} val0:{datastruct['sensor_values'][0]['val']} val1:{datastruct['sensor_values'][1]['val']}", end='')
        elif isinstance(datastruct, list):
            print(f"\rSending to {len(client_sockets)} clients[{num_pack}]{spinner_chars[num_pack % len(spinner_chars)]} val0:{datastruct[0]['val']} val1:{datastruct[1]['val']}", end='')
    except Exception:
        print(f"\rSending to {len(client_sockets)} clients[{num_pack}]{spinner_chars[num_pack % len(spinner_chars)]}", end='')
    for client_socket in client_sockets:
        try:
            client_socket.sendall(data.encode('utf-8'))
        except Exception as e:
            print(f"Error sending data to client: {e}")

def signal_handler(sig, frame):
    global server_running, server_socket
    print("Stopping server...")
    server_running = False
    if server_socket:
        server_socket.close()
    for client_socket in client_sockets:
        client_socket.close()
    sys.exit()

def accept_connections():
    global server_socket
    try:
        while server_running:
            client_socket, client_address = server_socket.accept()
            client_sockets.append(client_socket)
            client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            client_thread.start()
    except Exception as e:
        print(f"Error accepting connection: {e}")

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

    # Optionally scale Y for visibility
    # y = y * 5

    print(f"DEBUG: anchor1={anchor1}, anchor2={anchor2}, angle1={angle1_deg}, angle2={angle2_deg}, tag=({x:.2f}, {y:.2f})")
    return [x, y]

# --- Added: Connect to UI as a client ---
UI_HOST = "127.0.0.1"
UI_PORT = 12346

def connect_to_ui():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for _ in range(10):
        try:
            sock.connect((UI_HOST, UI_PORT))
            print("Connected to UI for real-time data.")
            return sock
        except ConnectionRefusedError:
            print("UI not ready, retrying...")
            time.sleep(1)
    raise Exception("Could not connect to UI after retries.")

def main():
    signal.signal(signal.SIGINT, signal_handler)
    global server_socket 
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('127.0.0.1', 12345))
    server_socket.listen(5)
    print("Server listening on port 12345")

    connection_thread = threading.Thread(target=accept_connections)
    connection_thread.start()

    print("Webserver started, start Bluetooth read")

    global sensors
    script_dir = os.path.dirname(__file__)
    json_file_path = os.path.join(script_dir, 'Sensor_Config.json')
    with open(json_file_path, 'r') as file:
        sensors = json.load(file)

    init_serials()
    temp=[None]
    last_angles = None
    last_time = time.time()
    distance_between_antennas = 0.5 

    # Generate a unique log file name for each run
    log_filename = f"tag_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    # --- Connect to UI for real-time data ---
    ui_sock = connect_to_ui()

    while True:
        try:
            val = getValues(temp)
            if val!=0:
                temp=val

                speed_along_line, last_angles, last_time = calculate_speed_along_line(temp, last_angles, distance_between_antennas, last_time)

                angle_antenna_1 = last_angles[0]['val']
                angle_antenna_2 = last_angles[1]['val']

                risk = calculate_risk_level(speed_along_line, angle_antenna_1, angle_antenna_2)

                for i in range(len(temp)):
                    temp[i]['speed_along_line'] = speed_along_line
                    temp[i]['risk_level'] = risk

                # --- Calculate tag position using triangulation ---
                anchor1_pos = temp[0]['pos']
                anchor2_pos = temp[1]['pos']
                tag_position = triangulate_position(anchor1_pos, anchor2_pos, angle_antenna_1, angle_antenna_2)

                # Compose the message as expected by the UI and logger
                message_final = json.dumps({
                    "point": {"position": tag_position, "Uncertainty": 0},
                    "sensor_values": temp
                })
                print(message_final)
                # --- Send to UI in real time ---
                try:
                    ui_sock.sendall(message_final.encode("utf-8"))
                except Exception as e:
                    print(f"Error sending to UI: {e}")

                # --- Compose and log the raw sensor data for replay ---
                raw_sensor_data = {
                    "anchors": [anchor1_pos, anchor2_pos],
                    "angles": [angle_antenna_1, angle_antenna_2],
                    "sensor_values": temp
                }
                log_data(raw_sensor_data, log_filename)
        except Exception as e:
            None

if __name__ == "__main__":
    main()