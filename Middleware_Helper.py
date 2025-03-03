# The purpose of this file is to separate the helper function. 
# The main code will be easy to read for both human and ChatGPT
import time
import os
import re
import socket
import xml.etree.ElementTree as ET
from datetime import datetime
import tkinter as tk
from tkinter import simpledialog, messagebox
import subprocess

MAX_LINES = 300  # Max number of lines to display 

########### 2. Helper function  ########## 

### 2.1 Prepare data input, CSV ###

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

### 2.3 Send data output to many types of target ###

# Persistent connection function with retry logic
def establish_tcp_connection(address, port, max_retries=5):
    wait_time = 2  # Initial wait time in seconds
    for attempt in range(max_retries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((address, port))
            print(f"Connected to {address}:{port} on attempt {attempt + 1}")
            return s, True
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error connecting to {address}:{port} - {e}")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60)  # Exponential backoff (capped at 60s)

    print(f"Failed to establish connection after {max_retries} attempts.")
    return None, False

# Send data over an already established TCP connection with reconnection logic
def send_data_tcp_persistent(socket_conn, data):
    try:
        if socket_conn:
            socket_conn.sendall(data.encode('utf-8'))  # Send data
            response = socket_conn.recv(1024).decode('utf-8')  # Receive response
            return response, True
        else:
            return "No active connection", False
    except Exception as e:
        print(f"Connection lost: {e}. Attempting to reconnect...")
        return str(e), False  # Indicate connection failure
    
# Send data over TCP and receive response
def send_data_tcp(address, port, data):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((address, port))
            s.sendall(data.encode('utf-8'))  # Send data to the target address and port
            response = s.recv(1024).decode('utf-8')  # Receive response from the target
            #update_display(text_area, f"Sent: {data[:-2]}")
            #update_display(text_area, f"Received: {response[:-1]}")
            return response, True
    except Exception as e:
        #update_display(text_area, f"Error sending data to {address}:{port} - {e}")
        return str(e), False

# Log events to a file for debugging and auditing
def log_event(log_dir, event):
    # Create the directory if it does not exist
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "app_log.txt")
    
    with open(log_file, "a") as f:
        f.write(f"{datetime.now()} - {event}\n")

def trim_message_display(text_area, max_lines):
    lines = text_area.get("1.0", tk.END).splitlines()
    if len(lines) > max_lines:
        text_area.delete("1.0", f"{max_lines + 1}.0")

def update_display(text_area, text):
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"[{timestamp}] {text}"

    text_area.insert(tk.END, message + "\n")    

    trim_message_display(text_area, MAX_LINES)  # Call this function to limit message lines
    text_area.see(tk.END)

### 2.4 Menu Item ###

def show_about():
    """Display About information."""
    messagebox.showinfo("About", "SPI Middleware v0.1\nDeveloped by Scapegoat MM")

def show_statistics():
    """Display Statistics information."""
    messagebox.showinfo("Statistics", "Processed: 100 files\nErrors: 2\nLast Update: 5 minutes ago")

def open_config():
    # """Open the configuration file using Notepad."""
    # config_file = "3_SPI_Middleware_setting.ini"
    
    # if os.path.exists(config_file):  # Check if the file exists
    #     os.system(f'notepad "{config_file}"')
    # else:
    #     messagebox.showerror("Error", f"Configuration file not found:\n{config_file}")

    """Ask for a password before opening the config file in Notepad."""
    password = simpledialog.askstring(" ", "Enter the password:", show="*")
    
    if password == "12345":
        subprocess.Popen(["notepad.exe", "3_SPI_Middleware_setting.ini"])
    else:
        messagebox.showerror("Access Denied", "Incorrect password!")