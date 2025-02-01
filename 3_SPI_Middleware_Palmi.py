import os
import shutil
import socket
import time
import configparser
from datetime import datetime
import threading
import tkinter as tk
from tkinter import scrolledtext
import xml.etree.ElementTree as ET
import re

############ 1. Variable Definition #############
# Read configuration from AOI_Middleware_setting.ini
config = configparser.ConfigParser()
config.read('3_SPI_Middleware_setting.ini')

source_dir = config.get('Source', 'Source_Dir')  # Source directory for input files
source_sub_dirs = [ssd.strip() for ssd in config.get('Source', 'Source_Sub_dir').split(',')]
file_types = [ft.strip() for ft in config.get('Source', 'File_Types').split(',')]
target_dir = config.get('Source', 'Target_Dir')  # Target directory for processed files
log_dir = config.get('Source', 'Log_Dir')  # Directory for storing log files
polling_interval = int(config.get('Source', 'Polling_Interval', fallback=5))  # Polling interval in seconds

xml_mappings = dict(config.items("PALMI_XML_Mapping"))

csv_result_0_conditions = [ft.strip() for ft in config.get('Pass_Condition', 'CSV_Result_0_If_FileEnd').split(',')]  # Conditions for determining serial state
xml_result_0_conditions = [ft.strip() for ft in config.get('Pass_Condition', 'XML_Result_0_If_ResultCode').split(',')]  # Conditions for determining serial state

hsc_address = config.get('Target', 'HSC_Address')  # Target address for TCP communication
hsc_ports = config.get('Target', 'HSC_Port').split(',')  # Ports for TCP communication per subdirectory

MAX_LINES = 300  # Max number of lines to display 

stop_event = threading.Event()
threads = []  # Store running threads
server_running = False
last_wait_time = None
wait_message_id = None
last_print_wait = False

########### 2. Helper function  ########## 

### 2.1 Prepare data input, CSV ###

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


### 2.2 Prepare data input, XML ###

def find_xml_files(root_dir):
    # Recursively find all XML files in the specified root directory.
    xml_files = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(".xml"):
                xml_files.append(os.path.join(root, file))
    return xml_files # Full directory structure and name

def extract_data_from_xml(file_path, xml_mappings):
    #Extracts data based on user-defined full XML paths in setting.ini.
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        extracted_data = []

        for key, xpath in xml_mappings.items():
            match = re.match(r"(.+?)\[@(.+?)\]", xpath)  # Match full path with attribute
            
            if match:
                element_path, attribute_name = match.groups()  # Extract element and attribute
            else:
                element_path, attribute_name = xpath, None  # If no attribute, extract text

            # Find the element in the XML tree
            element = root.find(element_path)
            
            if element is not None:
                if attribute_name:
                    extracted_data.append(element.get(attribute_name, "N/A"))  # Get attribute value
                else:
                    extracted_data.append(element.text.strip() if element.text else "N/A")  # Get text
            else:
                extracted_data.append("N/A")

        return extracted_data
    except ET.ParseError:
        print(f"Error parsing {file_path}")
    return ["N/A"] * len(xml_mappings)

# Determine serialNrState1 based on the result and predefined conditions
def determine_serial_state(result, result_0_conditions):
    return 0 if result in result_0_conditions else 1

### 2.3 Send data outpu to many types of target ###

# Send data over TCP and receive response
def send_data_tcp(address, port, data):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((address, port))
            s.sendall(data.encode('utf-8'))  # Send data to the target address and port
            response = s.recv(1024).decode('utf-8')  # Receive response from the target
            update_display(f"Sent: {data[:-2]}")
            update_display(f"Received: {response[:-1]}")
            return response, True
    except Exception as e:
        update_display(f"Error sending data to {address}:{port} - {e}")
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

def trim_message_display():
    lines = text_area.get("1.0", tk.END).splitlines()
    if len(lines) > MAX_LINES:
        text_area.delete("1.0", f"{MAX_LINES + 1}.0")

def update_display(text, replace_last=False):
    global wait_message_id, last_print_wait

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"[{timestamp}] {text}"

    if replace_last and wait_message_id is not None:
        text_area.delete(wait_message_id, text_area.index(f"{wait_message_id} lineend"))        
        text_area.insert(wait_message_id, message)
        last_print_wait = True
    else:
        if(last_print_wait):
            text_area.insert(tk.END, "\n")    
            last_print_wait = False
        text_area.insert(tk.END, message + "\n")
        wait_message_id = text_area.index("end-1c")  # Store the correct index of the new message

    trim_message_display()  # Call this function to limit message lines
    text_area.see(tk.END)

########### 3. Main structure management ##########

# Process XML files in a multi-level subdirectory, LOOP is here !
def process_subdir_xml(root_dir, target_root_dir, log_dir, xml_mappings, result_0_conditions, hsc_address, hsc_port, polling_interval):
    # event_id = 1  # Initialize event ID counter
    update_display(f"Start Monitoring XML: {root_dir}")

    while not stop_event.is_set():

        xml_files = find_xml_files(root_dir)

        for file_name in xml_files:
            
            if stop_event.is_set():
                return  # Exit thread immediately
            
            # Parse the filename into components
            start_Insptime, event_id, serial, result = extract_data_from_xml(file_name, xml_mappings)

            if not serial or not event_id or not result:
                update_display(f"Skipping invalid file : {file_name}")
                continue

            # Determine the serial state based on the result
            serial_nr_state = determine_serial_state(result, result_0_conditions)
            
            # Format data to send over TCP
            data = f"\x02uploadData;{event_id};-1;1;{serial};-1;{serial_nr_state};0;\x0D\x0A"

            # Send data to the target address and port
            response, connected = send_data_tcp(hsc_address, int(hsc_port), data)

            # Log the event details
            log_event(log_dir, f"File: {file_name}, Sent: {data}, Response: {response}, Connected: {connected}")

            if connected:
                # Move processed XML file to the target directory, maintaining subdirectory structure.
                relative_path = os.path.relpath(file_name, root_dir)  # Get relative path
                target_path = os.path.join(target_root_dir, relative_path)  # Construct target path

                os.makedirs(os.path.dirname(target_path), exist_ok=True)  # Create target directories if needed
                shutil.move(file_name, target_path)  # Move file
                update_display(f"Processed and moved file: {file_name}")

        # Wait for the specified polling interval before the next check
        time.sleep(polling_interval)

# Process CSV files in a single subdirectory, LOOP is here !
def process_subdir_csv(sub_dir, target_sub_dir, log_dir, result_0_conditions, hsc_address, hsc_port, polling_interval):
    event_id = 1  # Initialize event ID counter
    update_display(f"Start Monitoring CSV: {sub_dir}")

    while not stop_event.is_set():
        # Get sorted list of CSV files in the directory
        if not os.path.exists(sub_dir):
            os.makedirs(sub_dir)

        files = get_csv_files_sorted_by_date(sub_dir)

        for file_name, _ in files:
            # Parse the filename into components
            serial, datetime_part, result = parse_filename(file_name)
            if not serial or not datetime_part or not result:
                update_display(f"Skipping invalid file name: {file_name}")
                continue

            # Determine the serial state based on the result
            serial_nr_state = determine_serial_state(result, result_0_conditions)
            
            # Format data to send over TCP
            data = f"\x02uploadData;{event_id};-1;1;{serial};-1;{serial_nr_state};0;\x0D\x0A"

            # Send data to the target address and port
            response, connected = send_data_tcp(hsc_address, int(hsc_port), data)

            # Log the event details
            log_event(log_dir, f"File: {file_name}, Sent: {data}, Response: {response}, Connected: {connected}")

            if connected:
                # Move the file to the target directory only if the response was successful
                source_file = os.path.join(sub_dir, file_name)
                target_file = os.path.join(target_sub_dir, file_name)
                shutil.move(source_file, target_file)
                update_display(f"Processed and moved file: {file_name}")

                # Increment the event ID, looping back to 1 after 9999
                event_id = (event_id % 9999) + 1

        # Wait for the specified polling interval before the next check
        time.sleep(polling_interval)

# Master controller : Process files across all subdirectories using multi-threading
def process_files():

    global threads
    stop_event.clear()  # Reset stop event

    for idx, sub_dir in enumerate(source_sub_dirs):

        t_target = None
        t_args = None

        # Construct paths for the source and target subdirectories
        sub_dir_path = os.path.join(source_dir, sub_dir.strip())
        target_sub_dir = os.path.join(target_dir, sub_dir.strip())
        os.makedirs(target_sub_dir, exist_ok=True)  # Ensure target directory exists

        # Create a thread for processing each subdirectory
        if(file_types[idx] == 'CSV'):
            t_target = process_subdir_csv
            t_args = (sub_dir_path, target_sub_dir, log_dir, csv_result_0_conditions, hsc_address, hsc_ports[idx], polling_interval)

        elif (file_types[idx] == 'XML'):
            t_target = process_subdir_xml
            root_dir =  os.path.join(source_dir, source_sub_dirs[idx]) 
            target_root_dir = os.path.join(target_dir, source_sub_dirs[idx])  
            t_args = (root_dir, target_root_dir, log_dir, xml_mappings, xml_result_0_conditions, hsc_address, hsc_ports[idx], polling_interval)

        thread = threading.Thread(target=t_target, args=t_args, daemon=True)  # Mark thread as a daemon so it exits with the main program
        thread.start()
        threads.append(thread)

############ 4. GUI fucntion #############

def update_background(rgb):
    #Convert RGB tuple to hex and update background color of message windows.
    hex_color = f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'  # Convert (R, G, B) to #RRGGBB
    text_area.config(bg=hex_color)

def toggle_thread():
    global server_running, threads

    try:
        if server_running:
            start_button.config(text="Start")
            update_background((255, 255, 255))  # White
            stop_event.set()  # Signal threads to stop

            for thread in threads:
                thread.join(timeout=2)  # Wait for threads to finish
            threads = []  # Clear thread list

            server_running = False
            update_display("Stopped all monitoring threads.")
        else:
            process_files()
            start_button.config(text="Stop")
            update_background((204, 255, 230))  # Pale Green
            server_running = True
            update_display("Started monitoring threads.")
    except Exception as e:
        update_display(f"Error occurred: {e}")

# Initialize the Tkinter application
root = tk.Tk()
root.title("SPI Middleware")

frame = tk.Frame(root)
frame.pack(fill="both", expand=True, padx=10, pady=10)

text_area = scrolledtext.ScrolledText(frame, width=80, height=20)
text_area.pack(fill="both", expand=True)

start_button = tk.Button(frame, text="Start", command=toggle_thread, font=("Arial", 14), width=10, height=2)
start_button.pack(pady=5)

# Entry point for the application
if __name__ == "__main__":
    root.mainloop()