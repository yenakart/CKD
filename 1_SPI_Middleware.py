import os
import shutil
import socket
import time
from configparser import ConfigParser
from datetime import datetime
from threading import Thread
import tkinter as tk
from tkinter import scrolledtext

########### 1. Helper function to prepare data ########## 

# Load configuration from setting.txt
def load_config(config_file="1_SPI_Middleware_setting.ini"):
    config = ConfigParser()
    config.read(config_file)
    return config

# Read all .csv files from a directory sorted by modification date
def get_csv_files_sorted_by_date(directory):
    files = [f for f in os.listdir(directory) if f.endswith('.csv')]
    files_with_dates = [(f, os.path.getmtime(os.path.join(directory, f))) for f in files]
    return sorted(files_with_dates, key=lambda x: x[1])

# Parse filename into components (Serial, DATETIME, Result)
def parse_filename(filename):
    parts = filename.split('_')
    if len(parts) == 3:
        return parts[0], parts[1], parts[2].split('.')[0]
    return None, None, None

# Determine serialNrState1 based on the result and predefined conditions
def determine_serial_state(result, result_0_conditions):
    return 0 if result in result_0_conditions else 1

########### 2. Helper function to send data to many places ##########

# Send data over TCP and receive response
def send_data_tcp(address, port, data, status_window):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((address, port))
            s.sendall(data.encode('utf-8'))  # Send data to the target address and port
            response = s.recv(1024).decode('utf-8')  # Receive response from the target
            log_to_status_window(status_window, f"Sent: {data}")
            log_to_status_window(status_window, f"Received: {response}")
            return response, True
    except Exception as e:
        log_to_status_window(status_window, f"Error sending data to {address}:{port} - {e}")
        return str(e), False

# Log events to a file for debugging and auditing
def log_event(log_dir, event):
    # Create the directory if it does not exist
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "app_log.txt")
    
    with open(log_file, "a") as f:
        f.write(f"{datetime.now()} - {event}\n")

# Log messages to the status window
def log_to_status_window(status_window, message):
    status_window.insert(tk.END, f"{datetime.now()} - {message}\n")
    status_window.see(tk.END)

########### 3. Main structure management ##########

# Process files in a single subdirectory
def process_subdir(sub_dir, target_sub_dir, log_dir, result_0_conditions, hsc_address, hsc_port, polling_interval, status_window):
    event_id = 1  # Initialize event ID counter
    log_to_status_window(status_window, f"Start Monitoring: {sub_dir}")

    while True:
        # Get sorted list of CSV files in the directory
        if not os.path.exists(sub_dir):
            os.makedirs(sub_dir)

        files = get_csv_files_sorted_by_date(sub_dir)

        for file_name, _ in files:
            # Parse the filename into components
            serial, datetime_part, result = parse_filename(file_name)
            if not serial or not datetime_part or not result:
                log_to_status_window(status_window, f"Skipping invalid file name: {file_name}")
                continue

            # Determine the serial state based on the result
            serial_nr_state = determine_serial_state(result, result_0_conditions)
            
            # Format data to send over TCP
            data = f"\x02uploadData;{event_id};-1;1;{serial};-1;{serial_nr_state};0;\x0D\x0A"

            # Send data to the target address and port
            response, connected = send_data_tcp(hsc_address, int(hsc_port), data, status_window)

            # Log the event details
            log_event(log_dir, f"File: {file_name}, Sent: {data}, Response: {response}, Connected: {connected}")

            if connected:
                # Move the file to the target directory only if the response was successful
                source_file = os.path.join(sub_dir, file_name)
                target_file = os.path.join(target_sub_dir, file_name)
                shutil.move(source_file, target_file)
                log_to_status_window(status_window, f"Processed and moved file: {file_name}")

                # Increment the event ID, looping back to 1 after 9999
                event_id = (event_id % 9999) + 1

        # Wait for the specified polling interval before the next check
        time.sleep(polling_interval)

# Process files across all subdirectories using multi-threading
def process_files(config, status_window):
    source_dir = config.get('General', 'Source_Dir')  # Source directory for input files
    source_sub_dirs = config.get('General', 'Source_Sub_Dir').split(',')  # List of subdirectories to monitor
    target_dir = config.get('General', 'Target_Dir')  # Target directory for processed files
    log_dir = config.get('General', 'Log_Dir')  # Directory for storing log files
    polling_interval = int(config.get('General', 'Polling_Interval', fallback=100))  # Polling interval in seconds
    result_0_conditions = config.get('Format', 'Result_0_If_FileEnd').split(',')  # Conditions for determining serial state
    hsc_address = config.get('Target', 'HSC_Address')  # Target address for TCP communication
    hsc_ports = config.get('Target', 'HSC_Port').split(',')  # Ports for TCP communication per subdirectory

    threads = []  # List to store threads

    for idx, sub_dir in enumerate(source_sub_dirs):
        # Construct paths for the source and target subdirectories
        sub_dir_path = os.path.join(source_dir, sub_dir.strip())
        target_sub_dir = os.path.join(target_dir, sub_dir.strip())
        os.makedirs(target_sub_dir, exist_ok=True)  # Ensure target directory exists

        # Create a thread for processing each subdirectory
        thread = Thread(
            target=process_subdir,
            args=(sub_dir_path, target_sub_dir, log_dir, result_0_conditions, hsc_address, hsc_ports[idx], polling_interval, status_window),
            daemon=True  # Mark thread as a daemon so it exits with the main program
        )
        threads.append(thread)
        thread.start()  # Start the thread

# Tkinter application setup
def start_app():
    # Initialize the Tkinter application
    root = tk.Tk()
    root.title("File Processing Status")

    # Create a status window with a scrolled text widget
    status_window = scrolledtext.ScrolledText(root, width=100, height=30)
    status_window.pack(pady=10, padx=10)

    # Load the configuration file
    config = load_config()

    # Start the file processing threads
    Thread(target=process_files, args=(config, status_window), daemon=True).start()

    # Run the Tkinter main loop
    root.mainloop()

# Entry point for the application
if __name__ == "__main__":
    start_app()
