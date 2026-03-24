"""
RZ Autometadata - Auto Updater
Checks for updates via GitHub Releases API and handles download + install.
No Supabase dependency — 100% GitHub-based.
"""

import os
import sys
import tempfile
import logging
import subprocess

logger = logging.getLogger(__name__)

# App version — update setiap kali build EXE baru
CURRENT_VERSION = "1.0.0"

# GitHub repository info (CHANGE THIS to your actual repo)
GITHUB_REPO = "rezars19/rz-metadata"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def get_app_path():
    """Get the path of the current executable or script."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.abspath(sys.argv[0])


def is_frozen():
    """Check if running as compiled exe."""
    return getattr(sys, 'frozen', False)


def get_current_version():
    """Return current app version string."""
    return CURRENT_VERSION


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

        # Find the .exe asset
        download_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".exe"):
                download_url = asset.get("browser_download_url", "")
                break

        if not download_url:
            logger.warning("No .exe asset found in latest GitHub release")
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
        download_url: URL to download the new exe from
        on_progress: Optional callback(percent, downloaded_mb, total_mb)
    
    Returns:
        str: Path to downloaded file, or None on failure
    """
    try:
        import requests
        
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "RZAutometadata_update.exe")
        
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
        
        # Validate
        file_size = os.path.getsize(temp_file)
        if file_size < 1_000_000:
            logger.error(f"Downloaded file too small ({file_size} bytes)")
            os.remove(temp_file)
            return None
        
        with open(temp_file, 'rb') as f:
            header = f.read(2)
        
        if header != b'MZ':
            logger.error(f"Downloaded file is not a valid exe")
            os.remove(temp_file)
            return None
        
        logger.info(f"Download complete: {temp_file} ({file_size:,} bytes)")
        return temp_file
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None


def apply_update_and_restart(downloaded_file):
    """
    Replace current exe with downloaded update and restart.
    """
    if not is_frozen():
        logger.warning("Not running as exe, cannot auto-update.")
        return False
    
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
