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
SMOOTHING_WINDOW = 10  # More smoothing, less stutter

# Add this constant at the top (if not already present)
AXIS_OFFSET = 0.3   # vertical shift (fraction of canvas height)
AXIS_OFFSET_X = 0.4 # horizontal shift (fraction of canvas width)

show_visualization = True

# --- New smoothing parameters ---
SMOOTHING_ALPHA = 0.5 # Lower = smoother, higher = more responsive (try 0.3 to 0.5)
MAX_JUMP = 10.0         # Maximum allowed jump in world units (raw input)
MAX_Y_DELTA = 0.2       # Maximum allowed change in y per update (tune as needed)

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
            # Before appending to position_history:
            if position_history:
                prev_x, prev_y = position_history[-1]
                if abs(xpos - prev_x) > MAX_JUMP or abs(ypos - prev_y) > MAX_JUMP:
                    # Ignore this outlier
                    return
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
    Draw a stickman at the smoothed coordinates, color based on distance to truck.
    Uses exponential smoothing for less stuttering and more responsiveness.
    """
    global position_history
    canvas.delete("point")
    if not position_history:
        return

    # --- Exponential smoothing for position ---
    if position_history:
        alpha = SMOOTHING_ALPHA
        avg_x, avg_y = position_history[0]
        for px, py in position_history[1:]:
            avg_x = alpha * px + (1 - alpha) * avg_x
            # Clamp y movement
            new_avg_y = alpha * py + (1 - alpha) * avg_y
            if abs(new_avg_y - avg_y) > MAX_Y_DELTA:
                if new_avg_y > avg_y:
                    avg_y += MAX_Y_DELTA
                else:
                    avg_y -= MAX_Y_DELTA
            else:
                avg_y = new_avg_y

    # Get sensor positions (receivers)
    sensor_positions = [sensor.get('pos', [0, 0]) for sensor in last_sensor_values]

    # Calculate distance to each receiver (for stickman size)
    min_distance = float('inf')
    for sx, sy in sensor_positions:
        dist = math.hypot(avg_x - sx, avg_y - sy)
        if dist < min_distance:
            min_distance = dist

    # Stickman size mapping
    min_size = 30
    max_size = 90
    max_dist = 10  # adjust as needed

    if sensor_positions:
        size = max_size - (max_size - min_size) * min(min_distance, max_dist) / max_dist
        size = max(min_size, min(size, max_size))
    else:
        size = 30

    # --- Calculate distance to truck center (in world coordinates) ---
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()
    truck_x = canvas_width // 2 + 0      # x_offset from draw_truck
    truck_y = canvas_height // 2 + 80    # y_offset from draw_truck

    # Convert truck center to world coordinates
    truck_world_x = X_MIN + (truck_x / canvas_width) * (X_MAX - X_MIN)
    truck_world_y = Y_MIN + ((canvas_height * (1 - AXIS_OFFSET) - truck_y) / canvas_height) * (Y_MAX - Y_MIN)

    # Distance from stickman to truck center (in world coordinates)
    dist_to_truck = math.hypot(avg_x - truck_world_x, avg_y - truck_world_y)

    # --- Set color based on distance (red = close, yellow = medium, green = far) ---
    if dist_to_truck < 2.0:
        color = "red"
    elif dist_to_truck < 4.0:
        color = "yellow"
    else:
        color = "green"

    # --- Center the axes: place (0,0) at bottom center ---
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

    # After smoothing avg_x, avg_y
    ANTENNA_X_MIN = min([sensor.get('pos', [0, 0])[0] for sensor in last_sensor_values] or [X_MIN])
    ANTENNA_X_MAX = max([sensor.get('pos', [0, 0])[0] for sensor in last_sensor_values] or [X_MAX])
    ANTENNA_Y_MIN = min([sensor.get('pos', [0, 0])[1] for sensor in last_sensor_values] or [Y_MIN])
    ANTENNA_Y_MAX = max([sensor.get('pos', [0, 0])[1] for sensor in last_sensor_values] or [Y_MAX])

    # If tag is outside antenna x-range, clamp y to antenna y-range
    if avg_x < ANTENNA_X_MIN or avg_x > ANTENNA_X_MAX:
        avg_y = max(ANTENNA_Y_MIN, min(avg_y, ANTENNA_Y_MAX))

    # Get antenna x-range
    ANTENNA_XS = [sensor.get('pos', [0, 0])[0] for sensor in last_sensor_values]
    ANTENNA_X_MIN = min(ANTENNA_XS or [X_MIN])
    ANTENNA_X_MAX = max(ANTENNA_XS or [X_MAX])

    # Only update/draw if avg_x is within antenna range
    if not (ANTENNA_X_MIN <= avg_x <= ANTENNA_X_MAX):
        # Option 1: Don't update the stickman at all
        return
        # Option 2: Draw stickman at last valid position, or fade color, or show warning
        # color = "gray"

def visualize_sensors(sensor_values):
    """
    @brief Visualize sensor data on the canvas.
    @param sensor_values List of sensor data values.
    """
    global firstcall, show_visualization
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()
    graph_height = Y_MAX - Y_MIN
    graph_width = X_MAX - X_MIN
    canvas.delete("sensordata")
    if not show_visualization:
        canvas.delete("sensor")
        return
    # --- Use the same smoothing as for the stickman ---
    if position_history:
        alpha = SMOOTHING_ALPHA
        avg_x, avg_y = position_history[0]
        for px, py in position_history[1:]:
            avg_x = alpha * px + (1 - alpha) * avg_x
            avg_y = alpha * py + (1 - alpha) * avg_y
    else:
        avg_x, avg_y = 0, 0  # fallback

    for sensor in sensor_values:
        theta = math.radians(sensor.get('theta', 0))
        val = math.radians(sensor.get('val', 0))
        resAngle = theta + val
        xpos = sensor.get('pos', [0, 0])[0]
        ypos = sensor.get('pos', [0, 0])[1]

        # Calculate canvas coordinates for the sensor position
        canvas_x = (xpos - X_MIN) * (canvas_width / (X_MAX - X_MIN))
        canvas_y = canvas_height - ((ypos - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height) - (canvas_height * AXIS_OFFSET)
        aspect_ratio = canvas_width / canvas_height

        # Draw line from antenna to current tag position (stickman)
        # Use the same smoothed avg_x, avg_y as the stickman
        dx = avg_x - xpos
        dy = avg_y - ypos
        length = math.hypot(dx, dy)
        if length == 0:
            continue  # Avoid division by zero
        dx /= length
        dy /= length
        extend = max(X_MAX - X_MIN, Y_MAX - Y_MIN) * 2  # Large enough to cross canvas
        end_x_world = xpos + dx * extend
        end_y_world = ypos + dy * extend
        end_canvas_x = (end_x_world - X_MIN) * (canvas_width / (X_MAX - X_MIN))
        end_canvas_y = canvas_height - ((end_y_world - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height) - (canvas_height * AXIS_OFFSET)
        canvas.create_line(canvas_x, canvas_y, end_canvas_x, end_canvas_y, fill="black", width=2, tags="sensordata")

        if firstcall:
            # Draw green box
            canvas.create_rectangle(canvas_x - 5, canvas_y - 5, canvas_x + 5, canvas_y + 5, fill="green", tags="sensor")

            # Draw short lines around the sensor
            for angle in range(0, 360, 20):
                angle_rad = math.radians(angle)
                short_line_length = 50
                short_end_x = canvas_x + short_line_length * math.cos(angle_rad) * aspect_ratio
                short_end_y = canvas_y - short_line_length * math.sin(angle_rad) * (graph_width/graph_height)
                canvas.create_line(canvas_x, canvas_y, short_end_x, short_end_y, fill="black", tags="sensor")

                # Add angle labels
                label_x = canvas_x + (short_line_length + 10) * math.cos(angle_rad) * aspect_ratio
                label_y = canvas_y - (short_line_length + 10) * math.sin(angle_rad) * (graph_width/graph_height)
                angle_label = f"{angle}°"
                canvas.create_text(label_x, label_y, text=angle_label, fill="black", tags="sensor")
    firstcall = False

def draw_axes():
    """
    @brief Draw the coordinate axes on the canvas.
    """
    if not show_visualization:
        canvas.delete("axes")
        return
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()

    # --- Move the axes up a bit: add an offset to baseY ---
    baseX = (0 - X_MIN) / (X_MAX - X_MIN) * canvas_width
    baseY = (canvas_height * (1 - AXIS_OFFSET)) - ((0 - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height)

    # Draw x-axis (horizontal, through y=0)
    canvas.create_line(0, baseY, canvas_width, baseY, fill="black", tags="axes")

    # Draw y-axis (vertical, through x=0)
    canvas.create_line(baseX, 0, baseX, canvas_height, fill="black", tags="axes")

    # Draw x-axis ticks and labels
    for x in range(int(X_MIN), int(X_MAX) + 1):
        canvas_x = (x - X_MIN) / (X_MAX - X_MIN) * canvas_width
        canvas.create_line(canvas_x, baseY - TICK_SIZE, canvas_x, baseY + TICK_SIZE, fill="black", tags="axes")
        canvas.create_text(canvas_x, baseY + TICK_SIZE + 5, text=str(x), anchor="n", tags="axes")

    # Draw y-axis ticks and labels
    for y in range(int(Y_MIN), int(Y_MAX) + 1):
        canvas_y = (canvas_height * (1 - AXIS_OFFSET)) - ((y - Y_MIN) / (Y_MAX - Y_MIN) * canvas_height)
        canvas.create_line(baseX - TICK_SIZE, canvas_y, baseX + TICK_SIZE, canvas_y, fill="black", tags="axes")
        canvas.create_text(baseX - TICK_SIZE - 15, canvas_y, text=str(y), anchor="e", tags="axes")

    # --- Draw the truck after axes, before antennas ---
    draw_truck()

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

def toggle_visualization():
    global show_visualization, firstcall
    show_visualization = not show_visualization
    firstcall = False
    canvas.delete("axes")
    canvas.delete("sensor")
    canvas.delete("sensordata")
    draw_axes()
    visualize_sensors(last_sensor_values)

truck_img = None

def draw_truck():
    global truck_img
    canvas_width = canvas.winfo_width()
    canvas_height = canvas.winfo_height()

    # --- Truck image parameters ---
    truck_image_path = r"C:\Studienarbeit 2\Studienarbeit\Documents\truck.png"
    subsample_factor = 3  # Increase for smaller image, decrease for larger (must be integer)
    x_offset = 0          # Positive = right, negative = left, 0 = center
    y_offset = 80         # Positive = down, negative = up, 0 = center

    # Load the image only once
    if truck_img is None:
        img = tk.PhotoImage(file=truck_image_path)
        truck_img = img.subsample(subsample_factor, subsample_factor)

    # Draw the truck image
    x = canvas_width // 2 + x_offset
    y = canvas_height // 2 + y_offset
    canvas.create_image(x, y, image=truck_img, anchor="center", tags="truck")

def draw_stickman(x, y, scale=1.7):
    """
    Draw a stickman at canvas coordinates (x, y) with a given scale.
    """
    # Head
    head_radius = 18 * scale
    canvas.create_oval(
        x - head_radius, y - head_radius,
        x + head_radius, y + head_radius,
        fill="red", outline="red", tags="stickman"
    )
    # Body
    body_length = 40 * scale
    canvas.create_line(x, y + head_radius, x, y + head_radius + body_length, fill="red", width=3, tags="stickman")
    # Arms
    arm_length = 28 * scale
    arm_y = y + head_radius + 12 * scale
    canvas.create_line(x, arm_y, x - arm_length, arm_y + arm_length, fill="red", width=2, tags="stickman")
    canvas.create_line(x, arm_y, x + arm_length, arm_y + arm_length, fill="red", width=2, tags="stickman")
    # Legs
    leg_length = 32 * scale
    leg_y = y + head_radius + body_length
    canvas.create_line(x, leg_y, x - leg_length, leg_y + leg_length, fill="red", width=2, tags="stickman")
    canvas.create_line(x, leg_y, x + leg_length, leg_y + leg_length, fill="red", width=2, tags="stickman")

if __name__ == "__main__":
    # Initialize constants for the canvas
    POINT_SIZE = 5
    TICK_SIZE = 5
    X_MIN, X_MAX = -6, 10    # <--- Zoom out horizontally
    Y_MIN, Y_MAX = -2, 10   # <--- Zoom out vertically

    # Initialize Tkinter GUI
    root = tk.Tk()
    root.title("Coordinates Display")
    # Start in fullscreen mode
    root.attributes("-fullscreen", True)

    # --- Create a frame at the top for the coordinate label ---
    top_frame = tk.Frame(root, bg="white", height=40)
    top_frame.pack(side=tk.TOP, fill=tk.X)
    top_frame.pack_propagate(0)

    # Create a label for displaying coordinates (now in top_frame)
    label = tk.Label(top_frame, text="", font=("Arial", 14), bg="white")
    label.pack(side=tk.LEFT, padx=10, pady=10)

    # --- Create a frame at the bottom for buttons ---
    bottom_frame = tk.Frame(root, bg="white", height=60)
    bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
    bottom_frame.pack_propagate(0)

    # Button style
    button_bg = "#1976d2"
    button_fg = "white"
    button_font = ("Arial", 12, "bold")

    # Create a "Stop Simulation" button
    stop_button = tk.Button(bottom_frame, text="Stop Simulation", command=stop_simulation,
                            bg=button_bg, fg=button_fg, font=button_font)
    stop_button.pack(side=tk.LEFT, padx=10, pady=10)

    # Create a "Toggle Antennas/Coordinates" button
    toggle_button = tk.Button(bottom_frame, text="Toggle Antennas/Coordinates", command=toggle_visualization,
                              bg=button_bg, fg=button_fg, font=button_font)
    toggle_button.pack(side=tk.LEFT, padx=10, pady=10)

    # Create a canvas for displaying points (pack into root, NOT top_frame or bottom_frame)
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