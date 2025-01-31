# Version 2 : 25 Jan 25

import socket
import threading
import tkinter as tk
from tkinter import Button
from datetime import datetime
import time
import configparser

class FakeTCPServer:
    def __init__(self, master, config):
        self.master = master
        self.config = config
        self.ports = config['Ports']
        self.response_delay = config['Response_Delay'] / 1000  # Convert ms to seconds
        self.log_file = config['Log_File']
        self.server_threads = []
        self.running = False
        self.lock = threading.Lock()
        self.response_counters = {port: 0 for port in self.ports}

        # Tkinter setup
        self.master.geometry("1200x900")  # Make the window wider
        self.master.title("Fake TCP Server")
        self.frames = {}
        self.text_widgets = {}

        self.setup_monitor_windows()

        # Add Start and Stop buttons
        self.start_button = Button(master, text="Start", command=self.start_servers)
        self.start_button.grid(row=5, column=0, columnspan=2, pady=5)

        self.stop_button = Button(master, text="Stop", command=self.stop_servers)
        self.stop_button.grid(row=5, column=2, columnspan=2, pady=5)

        # Handle window close
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_monitor_windows(self):
        max_rows = 4
        cols = -(-len(self.ports) // max_rows)  # Calculate number of columns needed

        for idx, port in enumerate(self.ports):
            row = idx % max_rows
            col = idx // max_rows

            frame = tk.Frame(self.master, borderwidth=1, relief="solid")
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            label = tk.Label(frame, text=f"Port {port}")
            label.pack(anchor=tk.W)

            text_widget = tk.Text(frame, width=30, height=10)
            text_widget.pack(fill=tk.BOTH, expand=True)

            self.frames[port] = frame
            self.text_widgets[port] = text_widget

        for i in range(cols):
            self.master.columnconfigure(i, weight=1)


    def log_message(self, port, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.text_widgets[port].insert(tk.END, log_entry)
        self.text_widgets[port].see(tk.END)
        with open(self.log_file, "a") as log:
            log.write(log_entry)

    def handle_client(self, client_socket, port):
        while self.running:
            try:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                self.log_message(port, f"Received: {data}")

                # Parse message type
                if data.startswith("\x02uploadData;"):
                    response = self.handle_upload_data(port)
                elif data.startswith("\x02productStart;"):
                    response = self.handle_product_start(port)
                elif data.startswith("\x02uploadFailure;"):
                    response = self.handle_upload_failure(port)
                else:
                    response = "Unknown message type"

                time.sleep(self.response_delay)  # Introduce delay if configured
                client_socket.sendall(response.encode('utf-8'))
                self.log_message(port, f"Sent: {response}")
            except Exception as e:
                self.log_message(port, f"Error: {e}")
                break
        client_socket.close()

    def handle_upload_data(self, port):
        self.response_counters[port] += 1
        return f"{self.response_counters[port]:03d} ACK: Received uploadData"

    def handle_product_start(self, port):
        self.response_counters[port] += 1
        return f"{self.response_counters[port]:03d} ACK: Product started"

    def handle_upload_failure(self, port):
        self.response_counters[port] += 1
        return f"{self.response_counters[port]:03d} ACK: Upload failure received"

    def start_server(self, port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("0.0.0.0", port))
        server_socket.listen(5)
        server_socket.settimeout(1.0)
        self.log_message(port, f"Listening on port {port}")

        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                self.log_message(port, f"Connection from {addr}")
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, port))
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue  # Periodically check if the server is still running
            except Exception as e:
                self.log_message(port, f"Server error: {e}")
                break

        server_socket.close()
        self.log_message(port, f"Server on port {port} stopped")

    def start_servers(self):
        if self.running:
            return
        self.running = True
        for port in self.ports:
            server_thread = threading.Thread(target=self.start_server, args=(port,))
            server_thread.daemon = True
            self.server_threads.append(server_thread)
            server_thread.start()

    def stop_servers(self):
        self.running = False
        for thread in self.server_threads:
            thread.join(timeout=1)  # Timeout ensures GUI remains responsive
        self.server_threads = []
        # self.log_message(0, "All servers stopped")  # Example log for feedback

    def on_close(self):
        self.stop_servers()
        self.master.destroy()

# Read configuration from file using configparser
def read_config(file_path):
    parser = configparser.ConfigParser()
    parser.read(file_path)

    config = {
        'Ports': list(map(int, parser.get('Server', 'Ports').split(','))),
        'Response_Delay': parser.getint('Server', 'Response_Delay'),
        'Log_File': parser.get('Server', 'Log_File')
    }
    return config

# Entry point for Tkinter app
def main():
    root = tk.Tk()

    # Read configuration
    config = read_config("0_Fake_Server_setting.ini")

    app = FakeTCPServer(root, config)
    root.mainloop()

if __name__ == "__main__":
    main()
