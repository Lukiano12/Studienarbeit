"""
@file ui.py
@brief Mock UI module for displaying coordinates and sensor data
@date 2024-05-17
@author Christoph Gruender
"""

import json
import math
import socket
import threading
import time
import tkinter as tk
import subprocess

displaydebuginfo = 0
HOST = '127.0.0.1'  # localhost
PORT = 12346
firstcall = True

# Store the latest sensor values globally
last_sensor_values = []

# Smoothing for tag position
position_history = []
SMOOTHING_WINDOW = 5  # Increase for more smoothing, decrease for less lag

# Add this constant at the top (if not already present)
AXIS_OFFSET = 0.15  # 0.0 = bottom, 0.5 = center, 1.0 = top (fraction of canvas height)

def handle_client(conn, addr):
    print('Connected by', addr)
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            msg = data.decode()
            last_occurance = msg.rfind('{"point":')
            if last_occurance != -1:
                last_msg = msg[last_occurance:]
                if displaydebuginfo:
                    print("Received:", last_msg)
                print(f"{last_msg}\n", end='')
                update_display(last_msg)
            else:
                continue
    except Exception as e:
        print(f"Exception in client thread {addr}: {e}")
    finally:
        print(f"Connection closed: {addr}")
        conn.close()

def server_thread():
    """
    @brief Server thread function to handle incoming connections and data.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server listening on port {PORT}...")
        while True:
            try:
                conn, addr = s.accept()
                client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
            except Exception as e:
                print(f"Exception occurred: {e}. Continuing...")

def update_display(msg):
    """
    @brief Update the display with the received message.
    """
    global last_sensor_values, position_history
    try:
        # Parse the JSON message
        data = json.loads(msg)

        # Extract xpos and ypos from the 'point' dictionary
        xpos, ypos = data.get('point', {}).get('position', [None, None])
    
        # Check if xpos and ypos are not None
        if xpos is not None and ypos is not None:
            # Update the GUI with the received coordinates
            label.config(text=f"Xpos: {xpos}    Ypos: {ypos}    Uncertainty: {data.get('point', {}).get('Uncertainty', 'N/A')}")
            # Store sensor values for dot color/size calculation
            sensor_values = data.get('sensor_values', [])
            last_sensor_values = sensor_values
            # Update smoothing buffer with the latest position (from any client)
            position_history.append((xpos, ypos))
            if len(position_history) > SMOOTHING_WINDOW:
                position_history.pop(0)
            update_point_on_canvas()
            visualize_sensors(sensor_values)
        else:
            print("Invalid message format:", msg)

    except json.JSONDecodeError:
        print("Invalid JSON format:", msg)

def update_point_on_canvas():
    """
    Draw a stickman at the smoothed coordinates, always in red, no flashing.
    """
    global position_history
    canvas.delete("point")
    if not position_history:
        return
    avg_x = sum(p[0] for p in position_history) / len(position_history)
    avg_y = sum(p[1] for p in position_history) / len(position_history)

    # Get sensor positions (receivers)
    sensor_positions = [sensor.get('pos', [0, 0]) for sensor in last_sensor_values]

    # Calculate distance to each receiver
    min_distance = float('inf')
    for sx, sy in sensor_positions:
        dist = math.hypot(avg_x - sx, avg_y - sy)
        if dist < min_distance:
            min_distance = dist

    # Stickman size mapping
    min_size = 20
    max_size = 60
    max_dist = 10  # adjust as needed

    if sensor_positions:
        size = max_size - (max_size - min_size) * min(min_distance, max_dist) / max_dist
        size = max(min_size, min(size, max_size))
    else:
        size = 30

    # Always use red color, no flashing
    color = "#ff3333"

    # --- Center the axes: place (0,0) at bottom center ---
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()
    # X: 0 is at center, X increases to right, decreases to left
    # Y: 0 is at bottom, Y increases upwards
    canvas_x = (avg_x - X_MIN) / (X_MAX - X_MIN) * canvas_width
    canvas_y = canvas_height - ((avg_y - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height) - (canvas_height * AXIS_OFFSET)

    # Draw stickman (head, body, arms, legs)
    head_radius = size * 0.2
    body_length = size * 0.5
    arm_length = size * 0.35
    leg_length = size * 0.4

    # Head
    canvas.create_oval(
        canvas_x - head_radius, canvas_y - body_length - head_radius,
        canvas_x + head_radius, canvas_y - body_length + head_radius,
        fill=color, outline=color, tags="point"
    )
    # Body
    canvas.create_line(
        canvas_x, canvas_y - body_length + head_radius,
        canvas_x, canvas_y + body_length * 0.5,
        fill=color, width=2, tags="point"
    )
    # Arms
    canvas.create_line(
        canvas_x, canvas_y - body_length * 0.5,
        canvas_x - arm_length, canvas_y,
        fill=color, width=2, tags="point"
    )
    canvas.create_line(
        canvas_x, canvas_y - body_length * 0.5,
        canvas_x + arm_length, canvas_y,
        fill=color, width=2, tags="point"
    )
    # Left leg
    canvas.create_line(
        canvas_x, canvas_y + body_length * 0.5,
        canvas_x - leg_length * 0.5, canvas_y + body_length * 0.5 + leg_length,
        fill=color, width=2, tags="point"
    )
    # Right leg
    canvas.create_line(
        canvas_x, canvas_y + body_length * 0.5,
        canvas_x + leg_length * 0.5, canvas_y + body_length * 0.5 + leg_length,
        fill=color, width=2, tags="point"
    )

def visualize_sensors(sensor_values):
    """
    @brief Visualize sensor data on the canvas.
    @param sensor_values List of sensor data values.
    """
    # Clear existing sensor visualizations
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()
    graph_height = Y_MAX - Y_MIN
    graph_width = X_MAX - X_MIN
    canvas.delete("sensordata")
    global firstcall
    for sensor in sensor_values:
        theta = math.radians(sensor.get('theta', 0))
        val = math.radians(sensor.get('val', 0))
        resAngle = theta + val
        xpos = sensor.get('pos', [0, 0])[0]
        ypos = sensor.get('pos', [0, 0])[1]

        # Calculate canvas coordinates for the sensor position
        canvas_x = (xpos - X_MIN) * (canvas_width / (X_MAX - X_MIN))
        canvas_y = canvas_height - (ypos - Y_MIN) * (canvas_height / (Y_MAX - Y_MIN)) - (canvas_height * AXIS_OFFSET)
        aspect_ratio = canvas_width / canvas_height

        # Calculate endpoint of the line based on angle and length
        line_length = 5000  # Adjust as needed
        end_x = canvas_x + line_length * math.cos(resAngle) * aspect_ratio
        end_y = canvas_y - line_length * math.sin(resAngle) * (graph_width/graph_height)

        # Draw line originating from the box
        canvas.create_line(canvas_x, canvas_y, end_x, end_y, fill="black", tags="sensordata")

        if firstcall:
            # Draw green box
            canvas.create_rectangle(canvas_x - 5, canvas_y - 5, canvas_x + 5, canvas_y + 5, fill="green", tags="sensor")

            # Draw short lines around the sensor
            for angle in range(0, 360, 20):
                angle_rad = math.radians(angle)
                short_line_length = 50
                short_end_x = canvas_x + short_line_length * math.cos(angle_rad) *  aspect_ratio
                short_end_y = canvas_y - short_line_length * math.sin(angle_rad) * (graph_width/graph_height)
                canvas.create_line(canvas_x, canvas_y, short_end_x, short_end_y, fill="black", tags="sensor")

                # Add angle labels
                label_x = canvas_x + (short_line_length + 10) * math.cos(angle_rad) *  aspect_ratio
                label_y = canvas_y - (short_line_length + 10) * math.sin(angle_rad)* (graph_width/graph_height)
                angle_label = f"{angle}°"
                canvas.create_text(label_x, label_y, text=angle_label, fill="black", tags="sensor")
    firstcall = False

def draw_axes():
    """
    @brief Draw the coordinate axes on the canvas.
    """
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()

    # --- Move the axes up a bit: add an offset to baseY ---
    baseX = (0 - X_MIN) / (X_MAX - X_MIN) * canvas_width
    baseY = canvas_height - ((0 - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height) - (canvas_height * AXIS_OFFSET)

    # Draw x-axis (horizontal, through y=0)
    canvas.create_line(0, baseY, canvas_width, baseY, fill="black")

    # Draw y-axis (vertical, through x=0)
    canvas.create_line(baseX, 0, baseX, canvas_height, fill="black")

    # Draw x-axis ticks and labels
    for x in range(int(X_MIN), int(X_MAX) + 1):
        canvas_x = (x - X_MIN) / (X_MAX - X_MIN) * canvas_width
        canvas.create_line(canvas_x, baseY - TICK_SIZE, canvas_x, baseY + TICK_SIZE, fill="black")
        canvas.create_text(canvas_x, baseY + TICK_SIZE + 5, text=str(x), anchor="n")

    # Draw y-axis ticks and labels
    for y in range(int(Y_MIN), int(Y_MAX) + 1):
        canvas_y = canvas_height - ((y - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height) - (canvas_height * AXIS_OFFSET)
        canvas.create_line(baseX - TICK_SIZE, canvas_y, baseX + TICK_SIZE, canvas_y, fill="black")
        canvas.create_text(baseX - TICK_SIZE - 15, canvas_y, text=str(y), anchor="e")

previous_width = None
previous_height = None

def resize_updates(event):
    """
    @brief Handle window resize events to redraw the canvas content.
    """
    global previous_width, previous_height
    current_width = canvas.winfo_width()
    current_height = canvas.winfo_height()
    if current_width != previous_width or current_height != previous_height:
        previous_width = current_width
        previous_height = current_height
        print("Resize detected")
        canvas.delete("all")
        draw_axes()
        update_point_on_canvas()
        global firstcall
        firstcall = True

def main_thread():
    """
    @brief Main thread function for periodic print.
    """
    while True:
        print(".", end="", flush=True)
        time.sleep(1)

def stop_simulation():
    print("Stopping simulation...")
    root.destroy()
    subprocess.call("taskkill /F /IM python.exe", shell=True)
    subprocess.call("taskkill /F /IM cmd.exe", shell=True)

if __name__ == "__main__":
    # Initialize constants for the canvas
    POINT_SIZE = 5
    TICK_SIZE = 5
    X_MIN, X_MAX = -2, 6    # <--- Zoom out horizontally
    Y_MIN, Y_MAX = -2, 10   # <--- Zoom out vertically

    # Initialize Tkinter GUI
    root = tk.Tk()
    root.title("Coordinates Display")
    # Start in fullscreen mode
    root.attributes("-fullscreen", True)

    # Create a label for displaying coordinates
    label = tk.Label(root, text="", font=("Arial", 14))
    label.pack(pady=10)

    # Create a "Stop Simulation" button
    stop_button = tk.Button(root, text="Stop Simulation", command=stop_simulation, bg="red", fg="white", font=("Arial", 12, "bold"))
    stop_button.pack(pady=10)

    # Create a canvas for displaying points
    canvas = tk.Canvas(root, bg="white")
    canvas.pack(fill=tk.BOTH, expand=True)

    # Bind the resize event
    root.bind("<Configure>", resize_updates)

    # Start the server thread
    server_thread_obj = threading.Thread(target=server_thread)
    server_thread_obj.daemon = True
    server_thread_obj.start()

    # Start the main thread for printing dots
    main_thread_obj = threading.Thread(target=main_thread)
    main_thread_obj.daemon = True
    main_thread_obj.start()

    # Start the Tkinter event loop
    root.mainloop()