import os
import shutil
import socket
from configparser import ConfigParser
from datetime import datetime

# Load configuration from setting.txt
def load_config(config_file="setting.txt"):
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

# Determine serialNrState1 based on the result and config
def determine_serial_state(result, result_0_conditions):
    return 0 if result in result_0_conditions else 1

# Send data over TCP
def send_data_tcp(address, port, data):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((address, port))
            s.sendall(data.encode('utf-8'))
            print(f"Sent: {data}")
    except Exception as e:
        print(f"Error sending data to {address}:{port} - {e}")

# Main processing function
def process_files(config):
    source_dir = config.get('General', 'Source_dir')
    source_sub_dirs = config.get('General', 'Source_sub_dir').split(',')
    target_dir = config.get('General', 'Target_dir')
    result_0_conditions = config.get('Format', 'Result_0_If_FileEnd').split(',')
    hsc_address = config.get('Target', 'HSC_Address')
    hsc_ports = config.get('Target', 'HSC_Port').split(',')

    event_id = 1

    for idx, sub_dir in enumerate(source_sub_dirs):
        sub_dir_path = os.path.join(source_dir, sub_dir.strip())
        target_sub_dir = os.path.join(target_dir, sub_dir.strip())
        os.makedirs(target_sub_dir, exist_ok=True)

        files = get_csv_files_sorted_by_date(sub_dir_path)

        for file_name, _ in files:
            serial, datetime_part, result = parse_filename(file_name)
            if not serial or not datetime_part or not result:
                print(f"Skipping invalid file name: {file_name}")
                continue

            serial_nr_state = determine_serial_state(result, result_0_conditions)

            data = (f"\x02uploadData;{event_id};-1;1;{serial};-1;{serial_nr_state};0;\x0D\x0A")

            send_data_tcp(hsc_address, int(hsc_ports[idx]), data)

            # Move the file to the target directory
            source_file = os.path.join(sub_dir_path, file_name)
            target_file = os.path.join(target_sub_dir, file_name)
            shutil.move(source_file, target_file)

            print(f"Processed and moved file: {file_name}")
            event_id = (event_id % 9999) + 1

# Entry point
if __name__ == "__main__":
    config = load_config()
    process_files(config)