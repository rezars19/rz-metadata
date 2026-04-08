"""
RZ Autometadata - Auto Updater
Checks for updates via GitHub Releases API and handles download + install.
Supports both Windows and macOS.
No Supabase dependency — 100% GitHub-based.
"""

import os
import sys
import tempfile
import logging
import subprocess

logger = logging.getLogger(__name__)

# App version — update setiap kali build baru
CURRENT_VERSION = "1.0.3"

# GitHub repository info (CHANGE THIS to your actual repo)
GITHUB_REPO = "rezars19/rz-metadata"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Platform detection
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


def get_app_path():
    """Get the path of the current executable or script."""
    if getattr(sys, 'frozen', False):
        if IS_MACOS:
            # On macOS, sys.executable points to the binary inside .app bundle
            # Navigate up to get the .app path
            exe_path = sys.executable
            # e.g. /Applications/RZ Autometadata.app/Contents/MacOS/RZ Autometadata
            if ".app/Contents/MacOS" in exe_path:
                return exe_path.split(".app/Contents/MacOS")[0] + ".app"
            return exe_path
        return sys.executable
    else:
        return os.path.abspath(sys.argv[0])


def is_frozen():
    """Check if running as compiled exe/app."""
    return getattr(sys, 'frozen', False)


def get_current_version():
    """Return current app version string."""
    return CURRENT_VERSION


def _get_platform_asset_suffix():
    """Get the expected file suffix for the current platform's release asset."""
    if IS_MACOS:
        return ".dmg"
    else:
        return ".exe"


def check_for_updates():
    """
    Check GitHub Releases for a newer version.
    
    Returns:
        dict or None: Update info if available, None if up-to-date.
            {
                "version": "1.0.1",
                "release_notes": "...",
                "download_url": "...",
                "is_mandatory": False
            }
    """
    try:
        from packaging.version import Version
    except ImportError:
        logger.warning("packaging module not found, skipping update check")
        return None

    try:
        import requests
        response = requests.get(GITHUB_API_URL, timeout=15, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "RZAutometadata-Updater/1.0"
        })

        if response.status_code != 200:
            logger.warning(f"GitHub API returned {response.status_code}")
            return None

        data = response.json()
        tag = data.get("tag_name", "")  # e.g. "v1.0.1"
        version = tag.lstrip("v")  # "1.0.1"
        
        if not version:
            return None

        if Version(version) <= Version(CURRENT_VERSION):
            return None  # Already up-to-date

        # Get release notes
        release_notes = data.get("body", "")

        # Check if mandatory (look for [MANDATORY] in release body)
        is_mandatory = "[MANDATORY]" in release_notes.upper() if release_notes else False

        # Find the correct asset for this platform
        suffix = _get_platform_asset_suffix()
        download_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if IS_MACOS and ("macos" in name or "mac" in name or "darwin" in name) and name.endswith(".dmg"):
                download_url = asset.get("browser_download_url", "")
                break
            elif IS_WINDOWS and name.endswith(".exe"):
                download_url = asset.get("browser_download_url", "")
                break

        # Fallback: try any asset matching the platform suffix
        if not download_url:
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(suffix):
                    download_url = asset.get("browser_download_url", "")
                    break

        if not download_url:
            platform_name = "macOS (.dmg)" if IS_MACOS else "Windows (.exe)"
            logger.warning(f"No {platform_name} asset found in latest GitHub release")
            return None

        logger.info(f"Update available: v{CURRENT_VERSION} -> v{version}")

        return {
            "version": version,
            "release_notes": release_notes,
            "download_url": download_url,
            "is_mandatory": is_mandatory
        }

    except Exception as e:
        logger.warning(f"Update check failed: {e}")
        return None


def download_update(download_url, on_progress=None):
    """
    Download the update file from URL using requests.
    
    Args:
        download_url: URL to download the new exe/dmg from
        on_progress: Optional callback(percent, downloaded_mb, total_mb)
    
    Returns:
        str: Path to downloaded file, or None on failure
    """
    try:
        import requests
        
        temp_dir = tempfile.gettempdir()
        suffix = _get_platform_asset_suffix()
        temp_file = os.path.join(temp_dir, f"RZAutometadata_update{suffix}")
        
        logger.info(f"Downloading update from: {download_url}")
        
        response = requests.get(download_url, stream=True, timeout=120, headers={
            "User-Agent": "RZAutometadata-Updater/1.0",
            "Accept": "application/octet-stream"
        })
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            logger.error(f"Download URL returned HTML instead of binary!")
            return None
        
        total_size = int(response.headers.get('Content-Length', 0))
        
        if total_size > 0 and total_size < 1_000_000:
            logger.error(f"Download size too small ({total_size} bytes)")
            return None
        
        downloaded = 0
        block_size = 65536
        
        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if on_progress and total_size > 0:
                        percent = (downloaded / total_size) * 100
                        dl_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        on_progress(percent, dl_mb, total_mb)
        
        # Validate file size
        file_size = os.path.getsize(temp_file)
        if file_size < 1_000_000:
            logger.error(f"Downloaded file too small ({file_size} bytes)")
            os.remove(temp_file)
            return None
        
        # Validate file header
        with open(temp_file, 'rb') as f:
            header = f.read(4)
        
        if IS_WINDOWS:
            # Windows: check for MZ header (PE executable)
            if header[:2] != b'MZ':
                logger.error(f"Downloaded file is not a valid exe")
                os.remove(temp_file)
                return None
        elif IS_MACOS:
            # macOS DMG: various possible magic bytes
            # DMG files can start with different headers depending on format
            # Common: 'koly' footer, or zlib-compressed data
            # We just check it's not HTML or text
            if header[:1] == b'<' or header[:4] == b'<!DO':
                logger.error(f"Downloaded file appears to be HTML, not a valid DMG")
                os.remove(temp_file)
                return None
        
        logger.info(f"Download complete: {temp_file} ({file_size:,} bytes)")
        return temp_file
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None


def apply_update_and_restart(downloaded_file):
    """
    Replace current exe/app with downloaded update and restart.
    Supports both Windows (.exe) and macOS (.dmg).
    """
    if not is_frozen():
        logger.warning("Not running as exe/app, cannot auto-update.")
        return False
    
    if IS_WINDOWS:
        return _apply_update_windows(downloaded_file)
    elif IS_MACOS:
        return _apply_update_macos(downloaded_file)
    else:
        logger.warning(f"Auto-update not supported on {sys.platform}")
        return False


def _apply_update_windows(downloaded_file):
    """Apply update on Windows using batch script."""
    current_exe = get_app_path()
    backup_exe = current_exe + ".old"
    
    batch_script = os.path.join(tempfile.gettempdir(), "rz_metadata_updater.bat")
    
    script_content = f"""@echo off
title RZ Autometadata - Updating...
echo.
echo ============================================
echo   RZ Autometadata - Applying Update...
echo ============================================
echo.
echo Waiting for application to close...

:: Wait for the current exe to be released
:wait_loop
timeout /t 1 /nobreak >nul
tasklist /FI "PID eq %CURRENT_PID%" 2>nul | find /i "%CURRENT_PID%" >nul
if not errorlevel 1 goto wait_loop

:: Additional safety wait
timeout /t 2 /nobreak >nul

echo Backing up current version...
if exist "{backup_exe}" del /f /q "{backup_exe}"
move /y "{current_exe}" "{backup_exe}"

echo Installing new version...
move /y "{downloaded_file}" "{current_exe}"

echo Starting updated application...
start "" "{current_exe}"

:: Cleanup
timeout /t 3 /nobreak >nul
if exist "{backup_exe}" del /f /q "{backup_exe}"
del /f /q "%~f0"
exit
""".replace("%CURRENT_PID%", str(os.getpid()))
    
    try:
        with open(batch_script, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        logger.info(f"Starting updater script: {batch_script}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        
        subprocess.Popen(
            ['cmd', '/c', batch_script],
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to start updater: {e}")
        return False


def _apply_update_macos(downloaded_file):
    """Apply update on macOS using shell script."""
    current_app = get_app_path()  # e.g. /Applications/RZ Autometadata.app
    app_dir = os.path.dirname(current_app)
    app_name = os.path.basename(current_app)
    backup_app = current_app + ".old"
    
    # Mount point for DMG
    mount_point = os.path.join(tempfile.gettempdir(), "rz_metadata_mount")
    
    shell_script = os.path.join(tempfile.gettempdir(), "rz_metadata_updater.sh")
    
    script_content = f"""#!/bin/bash
# RZ Autometadata - macOS Update Script

echo "============================================"
echo "  RZ Autometadata - Applying Update..."
echo "============================================"

# Wait for the app to quit
echo "Waiting for application to close..."
while kill -0 {os.getpid()} 2>/dev/null; do
    sleep 1
done

# Additional safety wait
sleep 2

# Mount the DMG
echo "Mounting update DMG..."
mkdir -p "{mount_point}"
hdiutil attach "{downloaded_file}" -mountpoint "{mount_point}" -nobrowse -quiet

# Find the .app inside the DMG
APP_IN_DMG=$(find "{mount_point}" -maxdepth 1 -name "*.app" -type d | head -1)

if [ -z "$APP_IN_DMG" ]; then
    echo "ERROR: No .app found in DMG"
    hdiutil detach "{mount_point}" -quiet 2>/dev/null
    exit 1
fi

# Backup current app
echo "Backing up current version..."
if [ -d "{backup_app}" ]; then
    rm -rf "{backup_app}"
fi
mv "{current_app}" "{backup_app}"

# Copy new app
echo "Installing new version..."
cp -R "$APP_IN_DMG" "{app_dir}/"

# Unmount DMG
echo "Cleaning up..."
hdiutil detach "{mount_point}" -quiet 2>/dev/null

# Start updated app
echo "Starting updated application..."
open "{current_app}"

# Cleanup
sleep 3
if [ -d "{backup_app}" ]; then
    rm -rf "{backup_app}"
fi
rm -f "{downloaded_file}"
rm -f "{shell_script}"
"""
    
    try:
        with open(shell_script, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        os.chmod(shell_script, 0o755)
        
        logger.info(f"Starting updater script: {shell_script}")
        
        subprocess.Popen(
            ['/bin/bash', shell_script],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to start macOS updater: {e}")
        return False
