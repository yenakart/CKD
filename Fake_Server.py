import socket
import threading
import tkinter as tk
from datetime import datetime

class FakeTCPServer:
    def __init__(self, master, ports):
        self.master = master
        self.ports = ports
        self.server_threads = []
        self.running = True

        # Tkinter setup
        self.master.title("Fake TCP Server")
        self.frames = {}
        self.text_widgets = {}

        for port in ports:
            frame = tk.Frame(master)
            frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            label = tk.Label(frame, text=f"Port {port}")
            label.pack(anchor=tk.W)

            text_widget = tk.Text(frame, width=80, height=10)
            text_widget.pack(fill=tk.BOTH, expand=True)
            
            self.frames[port] = frame
            self.text_widgets[port] = text_widget

        self.start_servers()

    def log_message(self, port, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        text_widget = self.text_widgets[port]
        text_widget.insert(tk.END, log_entry)
        text_widget.see(tk.END)

    def handle_client(self, client_socket, port):
        while self.running:
            try:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                self.log_message(port, f"Received: {data}")

                response = f"ACK: Received your data"
                client_socket.sendall(response.encode('utf-8'))
                self.log_message(port, f"Sent: {response}")
            except Exception as e:
                self.log_message(port, f"Error: {e}")
                break
        client_socket.close()

    def start_server(self, port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("0.0.0.0", port))
        server_socket.listen(5)
        self.log_message(port, f"Listening on port {port}")

        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                self.log_message(port, f"Connection from {addr}")
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, port))
                client_thread.start()
            except Exception as e:
                self.log_message(port, f"Server error: {e}")
                break

        server_socket.close()

    def start_servers(self):
        for port in self.ports:
            server_thread = threading.Thread(target=self.start_server, args=(port,))
            server_thread.daemon = True
            self.server_threads.append(server_thread)
            server_thread.start()

    def stop_servers(self):
        self.running = False
        for thread in self.server_threads:
            thread.join()

# Entry point for Tkinter app
def main():
    root = tk.Tk()
    root.resizable(False, False)  # Make the window unresizable

    # List of ports to listen on
    ports = [3000, 3001, 3002, 3003, 3004]

    app = FakeTCPServer(root, ports)

    def on_close():
        app.stop_servers()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
