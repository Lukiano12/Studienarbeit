import json
import socket
import time
import sys
import os

if len(sys.argv) > 1:
    LOGFILE = sys.argv[1]
else:
    LOGFILE = "tag_log.jsonl"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12346  # Match the port in your UI

def connect_with_retry():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for _ in range(10):  # Try 10 times
        try:
            sock.connect((SERVER_HOST, SERVER_PORT))
            return sock
        except ConnectionRefusedError:
            print("Server not ready, retrying...")
            time.sleep(1)
    raise Exception("Could not connect to server after retries.")

def main():
    if not os.path.exists(LOGFILE):
        print(f"Log file '{LOGFILE}' not found.")
        return

    with open(LOGFILE, "r") as f:
        lines = f.readlines()

    sock = connect_with_retry()

    prev_time = None
    for line in lines:
        entry = json.loads(line)
        timestamp = entry["timestamp"]
        data = entry["data"]

        if prev_time is not None:
            time.sleep(max(0, timestamp - prev_time))
        prev_time = timestamp

        sock.sendall(json.dumps(data).encode("utf-8"))

    sock.close()

if __name__ == "__main__":
    main()