#!/bin/bash
# 🌀 Syntropia Installer Script
# Coordinates the installation of the Syntropia overlay node on CachyOS.

set -e

echo "=================================================="
echo "🌀 Syntropia: Starting Overlay Node Installation..."
echo "=================================================="

# Ensure script is run with root privileges
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: Please run this installation script as root (sudo)."
  exit 1
fi

# Detect Arch-based OS
if [ ! -f /etc/arch-release ]; then
  echo "⚠️ Warning: Syntropia is optimized for CachyOS and Arch-based systems."
  echo "Standard dependencies might need manual configuration."
fi

# Install system dependencies
echo "📦 Installing system dependencies..."
if command -v pacman &> /dev/null; then
  pacman -Sy --needed --noconfirm python python-pip python-psutil python-pydantic python-cryptography python-toml
else
  echo "⚠️ pacman not found. Please ensure Python and required dependencies are installed manually."
fi

# Create dedicated system user and group
echo "👤 Creating isolated system user 'syntropia'..."
if ! getent user syntropia > /dev/null; then
  useradd -r -s /usr/sbin/nologin -M -d /var/lib/syntropia syntropia
  echo "✔ User 'syntropia' created successfully."
else
  echo "✔ User 'syntropia' already exists."
fi

# Create required directories
echo "📁 Setting up system directories..."
mkdir -p /opt/syntropia
mkdir -p /etc/syntropia
mkdir -p /var/lib/syntropia
mkdir -p /var/log/syntropia

# Copy node code files to destination
echo "🚚 Deploying codebase to /opt/syntropia..."
cp -r src/ /opt/syntropia/
cp -r agents/ /opt/syntropia/
cp pyproject.toml /opt/syntropia/

# Deploy configuration file
if [ ! -f /etc/syntropia/config.toml ]; then
  echo "⚙️ Initializing configuration file in /etc/syntropia/config.toml..."
  cp config.toml.example /etc/syntropia/config.toml
else
  echo "⚙️ Existing configuration found. Skipping override."
fi

# Setup systemd services
echo "🖥️ Deploying systemd unit files..."
cp systemd/syntropia.service /etc/systemd/system/
cp systemd/syntropia-reaper.service /etc/systemd/system/

# Adjust file ownerships
echo "🔒 Restricting directory permissions..."
chown -R syntropia:syntropia /opt/syntropia /var/lib/syntropia /var/log/syntropia /etc/syntropia

# Reload and start services
echo "🔄 Reloading systemd and enabling syntropia.service & syntropia-reaper.service..."
systemctl daemon-reload
systemctl enable syntropia.service syntropia-reaper.service
systemctl restart syntropia.service syntropia-reaper.service

echo "=================================================="
echo "🌀 Syntropia Node & Reaper Daemon are installed and running!"
echo "--------------------------------------------------"
echo "💡 To check status: sudo systemctl status syntropia.service"
echo "💡 To view reaper:  sudo systemctl status syntropia-reaper.service"
echo "💡 To view logs:    sudo journalctl -u syntropia.service -f"
echo "=================================================="
