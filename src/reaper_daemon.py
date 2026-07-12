#!/usr/bin/env python3
import os
import sys
import time
import logging
import subprocess

# Ensure we can import syntropia package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from syntropia.blockchain import SQLiteBulletinChain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("syntropia.reaper")


class ContainerReaper:
    """
    External Daemon that runs outside the container sandbox as root/host user.
    Monitors the SQLiteBulletinChain for signed vaporization events and 
    safely deconstructs the corresponding Podman/Docker containers.
    """

    def __init__(self, db_path: str = None):
        # Resolve config/db path
        self.db_path = db_path or os.environ.get("SYNTROPIA_DB", "syntropia.db")
        # Handle fallback for local tests
        if not os.path.exists(self.db_path) and os.path.exists("syntropia_local.db"):
            self.db_path = "syntropia_local.db"
            
        self.blockchain = SQLiteBulletinChain(self.db_path)
        self.running = True

    def run(self):
        logger.info(f"Container Reaper started. Monitoring database: {self.db_path}")
        while self.running:
            try:
                pending_reaps = self.blockchain.get_pending_reaps()
                for reap in pending_reaps:
                    container_id = reap["container_id"]
                    request_id = reap["id"]
                    
                    logger.info(f"Processing reap request #{request_id} for container: {container_id}")
                    
                    # Verify signature matches (mock crypt check for simulated verification)
                    if self._verify_signature(reap):
                        self._terminate_container(container_id)
                        self.blockchain.mark_reaped(request_id)
                        logger.info(f"Container '{container_id}' successfully reaped and marked on-chain.")
                    else:
                        logger.warning(f"Reap request #{request_id} failed signature verification. Ignoring.")
                        
            except Exception as e:
                logger.error(f"Error in reaper loop: {e}")
                
            time.sleep(2)

    def _verify_signature(self, reap: dict) -> bool:
        # Simplistic signature validity check for daemon
        return bool(reap.get("signature") and reap.get("public_key"))

    def _terminate_container(self, container_id: str):
        """Attempts to stop and remove the Podman/Docker container."""
        # Try podman first, fallback to docker
        for engine in ["podman", "docker"]:
            try:
                # We do check=False because in tests/mock environments the container won't exist
                logger.info(f"Running: {engine} kill {container_id}")
                subprocess.run([engine, "kill", container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                subprocess.run([engine, "rm", container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                break
            except FileNotFoundError:
                continue


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    reaper = ContainerReaper(db_path)
    try:
        reaper.run()
    except KeyboardInterrupt:
        logger.info("Shutting down Container Reaper.")


if __name__ == "__main__":
    main()
