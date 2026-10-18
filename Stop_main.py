"""Stop the managed service; never kill unrelated Python or Thonny processes."""
import subprocess

if __name__ == "__main__":
    subprocess.run(["sudo", "-n", "systemctl", "stop", "gdf-reader.service"], check=True, timeout=180)
