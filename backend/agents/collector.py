import os
import time

class LogCollector:
    def __init__(self, logs_dir):
        self.logs_dir = logs_dir
        self.file_offsets = {}

    def watch(self):
        """Simple generator that yields new lines from .log files in the directory."""
        while True:
            for filename in os.listdir(self.logs_dir):
                if filename.endswith(".log"):
                    path = os.path.join(self.logs_dir, filename)
                    
                    # Initialize offset if new file
                    if path not in self.file_offsets:
                        self.file_offsets[path] = 0
                    
                    with open(path, 'r') as f:
                        f.seek(self.file_offsets[path])
                        new_lines = f.readlines()
                        self.file_offsets[path] = f.tell()
                        
                        for line in new_lines:
                            if line.strip():
                                yield filename, line.strip()
            time.sleep(1)

if __name__ == "__main__":
    # Quick test
    import os
    os.makedirs("logs", exist_ok=True)
    collector = LogCollector("logs")
    print("Collector initialized. Watching logs/...")
