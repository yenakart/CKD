# Version 4 : 2 Feb 25

import socket
import threading
import tkinter as tk
from tkinter import Button
from datetime import datetime
import time
import configparser
import random
import string
import pyodbc  # MSSQL connection

BACKROUND_COLOR = (230, 242, 255) # Pale blue

class FakeTCPServer:
    def __init__(self, master, config):
        self.master = master
        self.config = config
        
        self.machine_names = config['Machine_Names']
        self.ports = config['Ports']
        self.response_delay = config['Response_Delay'] / 1000  # Convert ms to seconds
        self.log_file = config['Log_File']

        self.db_connection_string = f"DRIVER={{SQL Server}};SERVER={config['MSSQL_Address']};DATABASE={config['MSSQL_DB']};UID={config['User']};PWD={config['Pwd']};"
        self.table_false = config['Table_False']
        self.server_threads = []
        self.response_counters = {port: 0 for port in self.ports}
        # Tkinter setup
        self.master.geometry("1200x700")  # Make the window wider
        self.master.title("Fake TCP Server")
        self.running = False
        self.frames = {}
        self.text_widgets = {}

        self.toggle_button = Button(master, text="Start", command=self.toggle_servers, font=("Arial", 14), width=10, height=2)
        self.toggle_button.grid(row=5, column=0, columnspan=1, pady=10)

        self.clear_button = Button(master, text="Clear", command=self.clear_logs, font=("Arial", 14), width=10, height=2)
        self.clear_button.grid(row=5, column=1, columnspan=1, pady=10)

        self.setup_monitor_windows()

        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_monitor_windows(self):
        max_rows = 4
        cols = -(-len(self.ports) // max_rows)  # Calculate number of columns needed

        for idx, port in enumerate(self.ports):
            row = idx % max_rows
            col = idx // max_rows

            frame = tk.Frame(self.master, borderwidth=1, relief="solid")
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            label = tk.Label(frame, text=f"AOI {idx+1} :Port {port}")
            label = tk.Label(frame, text=f"Port {port} : {self.machine_names[idx]}")
            label.pack(anchor=tk.W)

            text_widget = tk.Text(frame, width=30, height=7)
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

    def clear_logs(self):
        for text_widget in self.text_widgets.values():
            text_widget.delete("1.0", tk.END)

    def update_background(self, rgb):
        """Convert RGB tuple to hex and update background color of message windows."""
        hex_color = f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'  # Convert (R, G, B) to #RRGGBB
        for port in self.text_widgets:
            self.text_widgets[port].config(bg=hex_color)

    def toggle_servers(self):
        if self.running:
            self.stop_servers()
            self.toggle_button.config(text="Start")
            self.update_background((255, 255, 255))  # Change background to white when stopped
        else:
            self.start_servers()
            self.toggle_button.config(text="Stop")
            self.update_background(BACKROUND_COLOR)  # Change background to pale blue when running

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
                    response = self.handle_product_start(port, data)
                elif data.startswith("\x02uploadFailures;"):
                    response = self.handle_upload_failure(port)
                else:
                    response = "Unknown message type"

                time.sleep(self.response_delay)
                client_socket.sendall(response.encode('utf-8'))
                self.log_message(port, f"Sent: {response}")
            except Exception as e:
                self.log_message(port, f"Error: {e}")
                break
        client_socket.close()

	# Sub-routine to handle each message type
        
    def generate_random_serial(self):
        return ''.join(random.choices(string.ascii_uppercase, k=6)) + ''.join(random.choices(string.digits, k=9))

    def query_block_numbers(self, boardrecord):
        query = f"""
        SELECT BlockNumber, MIN(CAST(Confirm AS INT)) AS Total_Confirm
        FROM {self.table_false}
        WHERE BoardRecord = ?
        GROUP BY BlockNumber
        ORDER BY BlockNumber ASC
        """
        block_numbers = []
        
        try:
            with pyodbc.connect(self.db_connection_string) as conn: #Used with statements to auto-close DB connections.
                with conn.cursor() as cursor:
                    cursor.execute(query, (boardrecord,))
                    block_numbers = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"Database error: {e}")
        
        return block_numbers

    def handle_product_start(self, port, data):
        try:
            parts = data.strip().split(';')
            if len(parts) < 3:
                return "Error: Invalid data format"
            event_id, serial = parts[1], parts[2]
            block_numbers = self.query_block_numbers(event_id)
            serial_numbers = len(block_numbers)
            serial_data = [f"{self.generate_random_serial()};{block};0" for block in block_numbers]
            response = f"productStart;{event_id};0;OK;{serial_numbers};" + ';'.join(serial_data) + "\x0D\x0A"
            return response
        except Exception as e:
            return f"Error: {e}"
        
    def handle_upload_data(self, port):
        self.response_counters[port] += 1
        return f"{self.response_counters[port]:03d} ACK: Received uploadData\n"

    def handle_upload_failure(self, port):
        self.response_counters[port] += 1
        return f"{self.response_counters[port]:03d} ACK: Received Upload failures\n"

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
                continue
            except Exception as e:
                self.log_message(port, f"Server error: {e}")
                break
        server_socket.close()

    def start_servers(self):
        if self.running:
            return
        self.running = True
        for port in self.ports:
            thread = threading.Thread(target=self.start_server, args=(port,))
            thread.daemon = True
            self.server_threads.append(thread)
            thread.start()

    def stop_servers(self):
        self.running = False
        for thread in self.server_threads:
            thread.join(timeout=1)
        for port in self.ports: 
            self.log_message(port, f"Connection closed.")
        self.server_threads = []

    def on_close(self):
        self.stop_servers()
        self.master.destroy()

def read_config(file_path):
    parser = configparser.ConfigParser()
    parser.read(file_path)
    return {
        'MSSQL_Address': parser.get('DB_Server', 'MSSQL_Address'),
        'MSSQL_DB': parser.get('DB_Server', 'MSSQL_DB'),
        'User':parser.get('DB_Server', 'User'),
        'Pwd':parser.get('DB_Server', 'Pwd'),
        'Table_False':parser.get('DB_Server', 'Table_False'),
        
        'Machine_Names': [ft.strip() for ft in parser.get('HSC_Server', 'Machine_Names').split(',')],
        'Ports': list(map(int, parser.get('HSC_Server', 'Ports').split(','))),
        'Response_Delay': parser.getint('HSC_Server', 'Response_Delay'),
        'Log_File': parser.get('HSC_Server', 'Log_File')
    }

def main():
    root = tk.Tk()
    config = read_config("0_Fake_Server_setting.ini")
    app = FakeTCPServer(root, config)
    root.mainloop()

if __name__ == "__main__":
    main()