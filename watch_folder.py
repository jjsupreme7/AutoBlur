#!/usr/bin/env python3
"""
Folder watcher for AutoBlur.
Monitors the input folder and automatically processes new files of all supported formats.
"""

import time
import os
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from redactor.pipeline import redact_file, get_supported_extensions


class FileHandler(FileSystemEventHandler):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.processed = set()
        self.supported = get_supported_extensions()

    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()

        if ext not in self.supported:
            return

        if filepath in self.processed:
            return

        # Wait a moment for the file to finish writing
        time.sleep(0.5)

        if os.path.exists(filepath):
            self.processed.add(filepath)
            print(f"\n{'='*50}")
            print(f"New file detected: {os.path.basename(filepath)}")
            redact_file(filepath, self.output_dir)
            print(f"{'='*50}\n")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(script_dir, 'input')
    output_dir = os.path.join(script_dir, 'output')

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    supported = get_supported_extensions()

    print("=" * 50)
    print("  AUTO-BLUR FOLDER WATCHER")
    print("=" * 50)
    print(f"\nWatching: {input_dir}")
    print(f"Output:   {output_dir}")
    print(f"Formats:  {', '.join(sorted(supported))}")
    print("\nDrop files into the 'input' folder.")
    print("Redacted versions will appear in 'output'.")
    print("\nPress Ctrl+C to stop.\n")

    event_handler = FileHandler(output_dir)
    observer = Observer()
    observer.schedule(event_handler, input_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        observer.stop()

    observer.join()
    print("Done.")


if __name__ == "__main__":
    main()
