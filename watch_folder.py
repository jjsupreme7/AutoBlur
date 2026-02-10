#!/usr/bin/env python3
"""
Folder watcher for auto-blur.
Monitors the input folder and automatically processes new images.
"""

import time
import os
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from auto_blur import process_image

# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}

class ImageHandler(FileSystemEventHandler):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.processed = set()

    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()

        if ext not in IMAGE_EXTENSIONS:
            return

        # Avoid processing the same file multiple times
        if filepath in self.processed:
            return

        # Wait a moment for the file to finish writing
        time.sleep(0.5)

        if os.path.exists(filepath):
            self.processed.add(filepath)
            print(f"\n{'='*50}")
            print(f"New image detected!")
            process_image(filepath, self.output_dir)
            print(f"{'='*50}\n")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(script_dir, 'input')
    output_dir = os.path.join(script_dir, 'output')

    # Create directories if they don't exist
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 50)
    print("  AUTO-BLUR FOLDER WATCHER")
    print("=" * 50)
    print(f"\nWatching: {input_dir}")
    print(f"Output:   {output_dir}")
    print("\nDrop screenshots into the 'input' folder.")
    print("Blurred versions will appear in 'output'.")
    print("\nPress Ctrl+C to stop.\n")

    event_handler = ImageHandler(output_dir)
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
