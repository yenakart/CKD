import tkinter as tk
from tkinter import ttk, messagebox
import os
import random
import time
from datetime import datetime
from configparser import ConfigParser
import threading

stop_thread = False

def read_settings():
    config = ConfigParser()
    config.read("writer_setting.txt")

    source_dir = config.get("General", "Source_dir")
    source_sub_dirs = config.get("General", "Source_sub_dir").split(", ")

    results = config.get("Result_Percentage", "Result").split(", ")
    percentages = list(map(int, config.get("Result_Percentage", "Percentage").split(", ")))

    result_percentages = dict(zip(results, percentages))

    return source_dir, source_sub_dirs, result_percentages

def generate_result_code(result_percentages):
    total = sum(result_percentages.values())
    pick = random.randint(1, total)
    current = 0
    for result, weight in result_percentages.items():
        current += weight
        if pick <= current:
            return result

def generate_filename(result_code):
    random_number = str(random.randint(100000000, 999999999))
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"333240D001250{random_number}_{timestamp}_{result_code}.csv"

def write_files(file_count, interval, source_dir, source_sub_dirs, result_percentages, progress_var, progress_label):
    global stop_thread
    total_files = file_count * len(source_sub_dirs)
    completed_files = 0
    interval_per_file = interval / file_count  # Calculate the interval between files in the same directory

    for _ in range(file_count):
        if stop_thread:
            break
        
        for sub_dir in source_sub_dirs:
            if stop_thread:
                break

            full_dir = os.path.join(source_dir, sub_dir)
            if not os.path.exists(full_dir):
                os.makedirs(full_dir)

            result_code = generate_result_code(result_percentages)
            filename = generate_filename(result_code)
            filepath = os.path.join(full_dir, filename)
            with open(filepath, "w") as f:
                f.write(f"Result: {result_code}\n")

            completed_files += 1
            progress = int((completed_files / total_files) * 100)
            progress_var.set(progress)
            progress_label.config(text=f"Progress: {progress}%")
            time.sleep(interval_per_file / 1000)  # Wait for interval_per_file milliseconds

    send_button.config(state=tk.NORMAL)  # Re-enable the Send button after completion

def start_writing():
    global stop_thread
    stop_thread = False
    send_button.config(state=tk.DISABLED)  # Disable the Send button

    try:
        file_count = int(file_number_var.get())
        interval = int(interval_var.get())
        source_dir, source_sub_dirs, result_percentages = read_settings()

        progress_var.set(0)
        progress_label.config(text="Progress: 0%")

        thread = threading.Thread(target=write_files, args=(file_count, interval, source_dir, source_sub_dirs, result_percentages, progress_var, progress_label))
        thread.start()
    except Exception as e:
        messagebox.showerror("Error", str(e))
        send_button.config(state=tk.NORMAL)  # Re-enable the Send button

def stop_writing():
    global stop_thread
    stop_thread = True
    send_button.config(state=tk.NORMAL)  # Re-enable the Send button

# Create the GUI app
app = tk.Tk()
app.title("File Writer App")
app.resizable(False, False)  # Make the window unresizable

# Input for 'File number per line'
file_number_label = ttk.Label(app, text="File number per line:")
file_number_label.grid(row=0, column=0, padx=10, pady=10)
file_number_var = tk.StringVar()
file_number_entry = ttk.Entry(app, textvariable=file_number_var)
file_number_entry.grid(row=0, column=1, padx=10, pady=10)

# Input for 'Interval'
interval_label = ttk.Label(app, text="Unit-to-Unit Interval (ms):")
interval_label.grid(row=1, column=0, padx=10, pady=10)
interval_var = tk.StringVar()
interval_entry = ttk.Entry(app, textvariable=interval_var)
interval_entry.grid(row=1, column=1, padx=10, pady=10)

# Progress bar
progress_var = tk.IntVar()
progress_bar = ttk.Progressbar(app, variable=progress_var, maximum=100)
progress_bar.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

# Progress label
progress_label = ttk.Label(app, text="Progress: 0%")
progress_label.grid(row=3, column=0, columnspan=2, pady=10)

# Send button
send_button = ttk.Button(app, text="Send", command=start_writing)
send_button.grid(row=4, column=0, pady=20)

# Cancel button
cancel_button = ttk.Button(app, text="Cancel", command=stop_writing)
cancel_button.grid(row=4, column=1, pady=20)

app.mainloop()
