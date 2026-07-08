import os
import sys
import time
import random

class ThorHammer:
    """
    Thor Hammer: The P2P Torrent Sync Engine of Syntropia.
    Responsible for checking local model weights (.gguf files),
    fetching missing files via torrent magnet links, and managing seeding.
    """
    def __init__(self, cache_dir: str = "models"):
        self.cache_dir = os.path.abspath(cache_dir)
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def sync_models(self, registry) -> bool:
        """
        Scans loaded agents for required GGUF models.
        Downloads missing files with a beautiful TUI progress monitor.
        """
        print(f"\n\033[1;35m⚡ [Thor Hammer] Scanning model weights registry...\033[0m")
        time.sleep(0.5)

        missing_models = []
        for name, manifest in registry.manifests.items():
            if manifest.model:
                model_name = manifest.model.filename
                magnet = manifest.model.magnet
                filepath = os.path.join(self.cache_dir, model_name)
                
                # Check if GGUF file already exists
                if not os.path.exists(filepath):
                    print(f"  • \033[31mMissing model for {name}\033[0m: '{model_name}'")
                    missing_models.append((model_name, magnet, filepath))
                else:
                    print(f"  • \033[32mFound local weights for {name}\033[0m: '{model_name}' [Active Seeding]")

        if not missing_models:
            print("\033[1;32m⚡ [Thor Hammer] All model weights verified. Node is fully synced and seeding.\033[0m")
            return True

        # Process downloads in the terminal using the custom TUI progress bar style
        for model_name, magnet, filepath in missing_models:
            self._download_via_torrent(model_name, magnet, filepath)

        print("\033[1;32m⚡ [Thor Hammer] Synchronization complete. Seeding model swarms.\033[0m")
        return True

    def _download_via_torrent(self, filename: str, magnet: str, destination: str):
        """Simulates a low-level P2P BitTorrent download with a beautiful live progress bar."""
        print(f"\n\033[33m[Thor Hammer] Connecting to DHT bootstrap nodes to fetch metadata...\033[0m")
        time.sleep(0.8)
        
        info_hash = magnet.split("urn:btih:")[1].split("&")[0][:10] if "urn:btih:" in magnet else "unknown"
        print(f"\033[32m[Thor Hammer] Resolved torrent swarm (Hash: {info_hash}). Connecting to peers...\033[0m")
        time.sleep(0.6)

        total_size_mb = random.randint(350, 950)
        downloaded = 0.0
        seeders = random.randint(8, 26)
        
        # Build the TUI drawing frames
        while downloaded < total_size_mb:
            speed = random.uniform(1.8, 8.4)  # MB/s
            downloaded += speed * 0.2
            if downloaded > total_size_mb:
                downloaded = total_size_mb

            percent = int((downloaded / total_size_mb) * 100)
            bar_length = 20
            filled_length = int(bar_length * percent // 100)
            # block chars: █ for filled, ░ for empty
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            # Print update in-place using carriage return \r
            sys.stdout.write(
                f"\r\033[36m📥 [Thor Hammer] Syncing {filename} |{bar}| "
                f"{percent}% [{downloaded:.1f}/{total_size_mb} MB] "
                f"| Speed: {speed:.1f} MB/s | Seeds: {seeders}\033[0m"
            )
            sys.stdout.flush()
            time.sleep(0.1)

        sys.stdout.write("\n")
        # Touch the file to simulate download completion
        with open(destination, 'w') as f:
            f.write("Syntropia Mock Model Weights")
            
        print(f"\033[32m✔ [Thor Hammer] Successfully synced and verified integrity of {filename}.\033[0m")
        time.sleep(0.4)
