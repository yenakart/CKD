import os
import shutil

import time
import configparser
from datetime import datetime
import threading
import tkinter as tk
from tkinter import scrolledtext

from Middleware_Helper import get_csv_files_sorted_by_date, parse_filename, find_xml_files, extract_data_from_xml, determine_serial_state
from Middleware_Helper import send_data_tcp, log_event, update_display
from Middleware_Helper import show_about, show_statistics, open_config

############ 1. Variable Definition #############

config = configparser.ConfigParser() # Need to read at program opening to draw the machine rectangles
config.read('1_SPI_Middleware_setting.ini')

source_dir = None
source_sub_dirs = []
file_types = []
target_dir = None
log_dir = None
polling_interval = None
xml_mappings = {}
csv_result_0_conditions = []
xml_result_0_conditions = []
standby_time = None
unknown_time = None
hsc_address = None
hsc_ports = []
machine_names = [ft.strip() for ft in config.get('HSC_Server', 'Machine_Names').split(',')]
machine_types = []
machine_updates = []
machine_statuses = []
machine_rects = []

stop_event = threading.Event()
threads = []  # Store running threads
server_running = False
wait_message_id = None
last_print_wait = False

########### 3. Main structure management ##########

# Process XML files in a multi-level subdirectory, LOOP is here !
def process_subdir_xml(idx, root_dir, target_root_dir, log_dir, xml_mappings, result_0_conditions, hsc_address, hsc_port, polling_interval):

    update_display(text_area, f"Start Monitoring XML: {root_dir}")

    while not stop_event.is_set():

        update_rectangles(idx)

        xml_files = find_xml_files(root_dir)

        for file_name in xml_files: # Case 2 : New file to process
            
            if stop_event.is_set():
                return  # Exit thread immediately
            
            # Parse the filename into components
            start_Insptime, event_id, serial, result = extract_data_from_xml(file_name, xml_mappings)

            if not serial or not event_id or not result:
                update_display(text_area, f"Skipping invalid file : {file_name}")
                machine_statuses[idx] = "File_issue"
                machine_rects[idx].config(text=f"{machine_names[idx]}\n0 s", bg="orange") # Update GUI rectangle
                continue

            # Determine the serial state based on the result
            serial_nr_state = determine_serial_state(result, result_0_conditions)
            
            # Format data to send over TCP
            data = f"\x02uploadData;{event_id};-1;1;{serial};-1;{serial_nr_state};0;\x0D\x0A"

            # Send data to the target address and port
            response, connected = send_data_tcp(hsc_address, int(hsc_port), data)
            update_display(text_area, f"{machine_names[idx]} : {data[1:-2]}") # No need for \x0D\x0A
            # update_display(text_area, f"iTac  : {response}---------------------------------")

            # Log the event details
            log_event(log_dir, f"File: {file_name}, Sent: {data}, Response: {response}, Connected: {connected}")

            if connected:
                # Move processed XML file to the target directory, maintaining subdirectory structure.
                relative_path = os.path.relpath(file_name, root_dir)  # Get relative path
                target_path = os.path.join(target_root_dir, relative_path)  # Construct target path

                os.makedirs(os.path.dirname(target_path), exist_ok=True)  # Create target directories if needed
                shutil.move(file_name, target_path)  # Move file
                # update_display(text_area, f"Processed and moved file: {file_name}")

                machine_updates[idx] = datetime.now()
                machine_statuses[idx] = "OK"
                machine_rects[idx].config(text=f"{machine_names[idx]}\n0 s", bg="green") # Update GUI rectangle
            else :
                machine_statuses[idx] = "Error"
                machine_rects[idx].config(text=f"{machine_names[idx]}\n0 s", bg="red") # Update GUI rectangle

        # Wait for the specified polling interval before the next check
        time.sleep(polling_interval)

# Process CSV files in a single subdirectory, LOOP is here !
def process_subdir_csv(idx, sub_dir, target_sub_dir, log_dir, result_0_conditions, hsc_address, hsc_port, polling_interval):
    event_id = 1  # Initialize event ID counter
    update_display(text_area, f"Start Monitoring CSV: {sub_dir}")

    while not stop_event.is_set():

        update_rectangles(idx)

        #if not os.path.exists(sub_dir): 
        #    os.makedirs(sub_dir)

        files = get_csv_files_sorted_by_date(sub_dir)

        for file_name, _ in files:
            # Parse the filename into components
            serial, datetime_part, result = parse_filename(file_name)
            if not serial or not datetime_part or not result:
                update_display(text_area, f"Skipping invalid file name: {file_name}")
                continue

            # Determine the serial state based on the result
            serial_nr_state = determine_serial_state(result, result_0_conditions)
            
            # Format data to send over TCP
            data = f"\x02uploadData;{event_id};-1;1;{serial};-1;{serial_nr_state};0;\x0D\x0A"

            # Send data to the target address and port
            response, connected = send_data_tcp(hsc_address, int(hsc_port), data)
            update_display(text_area, f"{machine_names[idx]} : {data[1:-2]}") # No need for \x0D\x0A
            # update_display(text_area, f"iTac  : {response}---------------------------------")

            # Log the event details
            log_event(log_dir, f"File: {file_name}, Sent: {data}, Response: {response}, Connected: {connected}")

            if connected:
                # Move the file to the target directory only if the response was successful
                source_file = os.path.join(sub_dir, file_name)
                target_file = os.path.join(target_sub_dir, file_name)
                shutil.move(source_file, target_file)
                #update_display(text_area, f"Processed and moved file: {file_name}")

                # Increment the event ID, looping back to 1 after 9999
                event_id = (event_id % 9999) + 1
                machine_updates[idx] = datetime.now()
                machine_statuses[idx] = "OK"    
                machine_rects[idx].config(text=f"{machine_names[idx]}\n0 s", bg="green") # Update GUI rectangle            
            else :
                machine_statuses[idx] = "Error"
                machine_rects[idx].config(text=f"{machine_names[idx]}\n0 s", bg="red") # Update GUI rectangle

        # Wait for the specified polling interval before the next check
        time.sleep(polling_interval)

# Master controller : Process files across all subdirectories using multi-threading
def process_files():

    global config, source_dir, source_sub_dirs, file_types, target_dir, log_dir
    global polling_interval, xml_mappings, csv_result_0_conditions, xml_result_0_conditions
    global standby_time, unknown_time, hsc_address, hsc_ports, machine_names, machine_types, machine_updates, machine_statuses
    global threads, stop_event

    # Reload configuration
    config = configparser.ConfigParser()
    config.read('1_SPI_Middleware_setting.ini')

    source_dir = config.get('Source', 'Source_Dir')  # Source directory for input files
    source_sub_dirs = [ssd.strip() for ssd in config.get('Source', 'Source_Sub_dir').split(',')]
    file_types = [ft.strip() for ft in config.get('Source', 'File_Types').split(',')]
    target_dir = config.get('Source', 'Target_Dir')  # Target directory for processed files
    log_dir = config.get('Source', 'Log_Dir')  # Directory for storing log files
    polling_interval = int(config.get('Source', 'Polling_Interval', fallback=5))  # Polling interval in seconds
    xml_mappings = dict(config.items("PALMI_XML_Mapping"))
    csv_result_0_conditions = [ft.strip() for ft in config.get('Pass_Condition', 'CSV_Result_0_If_FileEnd').split(',')]  # Conditions for determining serial state
    xml_result_0_conditions = [ft.strip() for ft in config.get('Pass_Condition', 'XML_Result_0_If_ResultCode').split(',')]  # Conditions for determining serial state
    standby_time= int(config.get('Machine_State_Time', 'Standby_Time', fallback=600)) # 10 Min
    unknown_time= int(config.get('Machine_State_Time', 'Unknown_Time', fallback=1800)) # 30 Min
    hsc_address = config.get('HSC_Server', 'HSC_Address')  # Target address for TCP communication
    hsc_ports = config.get('HSC_Server', 'HSC_Port').split(',')  # Ports for TCP communication per subdirectory
    machine_names = [ft.strip() for ft in config.get('HSC_Server', 'Machine_Names').split(',')]
    machine_types = [ft.strip() for ft in config.get('HSC_Server', 'Machine_Types').split(',')]
    machine_updates = [datetime.now()] * len(machine_names)
    machine_statuses = ["Unknown"] * len(machine_names)

    stop_event.clear()  # Reset stop event
    threads = []  # Clear old threads

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
            t_args = (idx, sub_dir_path, target_sub_dir, log_dir, csv_result_0_conditions, hsc_address, hsc_ports[idx], polling_interval)

        elif (file_types[idx] == 'XML'):
            t_target = process_subdir_xml
            root_dir =  os.path.join(source_dir, source_sub_dirs[idx]) 
            target_root_dir = os.path.join(target_dir, source_sub_dirs[idx])  
            t_args = (idx, root_dir, target_root_dir, log_dir, xml_mappings, xml_result_0_conditions, hsc_address, hsc_ports[idx], polling_interval)

        thread = threading.Thread(target=t_target, args=t_args, daemon=True)  # Mark thread as a daemon so it exits with the main program
        thread.start()
        threads.append(thread)

############ 4. GUI function #############
# Update machine rectangles on GUI
def update_rectangles(idx):

    elapsed_time = (datetime.now() - machine_updates[idx]).seconds

    # Determine color based on elapsed time
    if machine_statuses[idx] == "Error":
        color = "red"
    elif machine_statuses[idx] == "File_issue":
        color = "orange"
    elif elapsed_time > unknown_time: 
        machine_statuses[idx] = "Unknown"
        color = "grey"
    elif elapsed_time > standby_time and machine_statuses[idx] == "OK":
        machine_statuses[idx] = "Standby"
        color = "yellow"
    elif machine_statuses[idx] == "OK":
        color = "green"
    else: 
        color = "grey"

    machine_rects[idx].config(text=f"{machine_names[idx]}\n{elapsed_time} s", bg=color) # Update GUI rectangle

def update_background(rgb):
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
            update_display(text_area, "Stopped all monitoring threads.")
        else:
            process_files()
            start_button.config(text="Stop")
            update_background((204, 255, 230))  # Pale Green
            server_running = True
            update_display(text_area, "Started monitoring threads.")
    except Exception as e:
        update_display(text_area, f"Error occurred: {e}")

# 0. Initialize the Tkinter application
root = tk.Tk()
root.title("SPI Middleware")
root.minsize(width=700, height=240)  # User cannot resize below 1000x500
root.geometry("700x240") # Initial size

# 1.Create a top-level menu
menu_bar = tk.Menu(root)

file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Config", command=open_config)

help_menu = tk.Menu(menu_bar, tearoff=0)
help_menu.add_command(label="About", command=show_about)
help_menu.add_command(label="Statistics", command=show_statistics)

menu_bar.add_cascade(label="File", menu=file_menu)
menu_bar.add_cascade(label="Help", menu=help_menu)

root.config(menu=menu_bar)

# 2. Frame for machine indicators
status_frame = tk.Frame(root)
status_frame.pack(pady=5)

for i, name in enumerate(machine_names):
    machine_rect = tk.Label(status_frame, text=f"{name}\n0s", bg="grey", fg="white", width=10, height=3, relief="ridge")
    machine_rect.grid(row=0, column=i, padx=5, pady=5)
    machine_rects.append(machine_rect)

frame = tk.Frame(root)
frame.pack(fill="both", expand=True, padx=10, pady=10)

# 3. Button for 'Start/Stop' and 'Clear'
def clear_text():
    text_area.delete(1.0, tk.END)

# Start/Stop and Clear buttons
button_frame = tk.Frame(frame)
button_frame.pack(pady=5)

start_button = tk.Button(button_frame, text="Start", command=toggle_thread, font=("Arial", 14), width=30, height=1)
start_button.pack(side="left", padx=5)

clear_button = tk.Button(button_frame, text="Clear", command=clear_text, font=("Arial", 14), width=30, height=1)
clear_button.pack(side="left", padx=5)

# 4. Frame for message windows
text_area = scrolledtext.ScrolledText(frame, width=80, height=20)
text_area.pack(fill="both", expand=True, pady=10)

# Entry point for the application
if __name__ == "__main__":
    root.mainloop()