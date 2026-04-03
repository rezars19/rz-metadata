"""
RZ Autometadata - Build Script
Build the application into a standalone exe (Windows) or .app (macOS) using PyInstaller.

Usage:
    python build.py
"""

import subprocess
import sys
import os
import shutil
import stat
import time

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


def remove_readonly(func, path, _):
    """Clear the readonly bit and reattempt the removal"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def main():
    platform_name = "macOS" if IS_MACOS else "Windows"
    print("=" * 60)
    print(f"  RZ Autometadata - Build for {platform_name}")
    print("=" * 60)
    print()

    # Clean old builds
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"[*] Cleaning {folder}/...")
            try:
                shutil.rmtree(folder, onerror=remove_readonly)
            except PermissionError:
                print(f"[!] Could not clean {folder}. Retrying in 2 seconds...")
                time.sleep(2)
                try:
                    shutil.rmtree(folder, onerror=remove_readonly)
                except Exception as e:
                    print(f"[!] Warning: Could not fully clean {folder}: {e}")

    # Build command — platform-specific
    if IS_MACOS:
        # macOS: --add-data uses : separator, use .icns icon, onedir for .app bundle
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name=RZ Autometadata",
            "--onedir",                     # .app bundle (macOS standard)
            "--windowed",                   # No terminal window
            f"--icon=icon.icns",            # macOS icon format
            "--add-data=icon.icns:.",        # Include icon for runtime
            "--add-data=logo.png:.",         # Include logo for runtime
            # Hidden imports for libraries that PyInstaller might miss
            "--hidden-import=customtkinter",
            "--hidden-import=PIL",
            "--hidden-import=PIL._tkinter_finder",
            "--hidden-import=cv2",
            "--hidden-import=numpy",
            "--hidden-import=packaging",
            "--hidden-import=packaging.version",
            "--hidden-import=tkinterdnd2",
            "--hidden-import=psd_tools",
            # Collect all customtkinter data files (themes, etc.)
            "--collect-all=customtkinter",
            "--collect-all=tkinterdnd2",
            # Main script
            "app.py"
        ]
    else:
        # Windows: --add-data uses ; separator, use .ico icon, onefile for single exe
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name=RZ Autometadata",
            "--onefile",                    # Single exe file
            "--windowed",                   # No console window
            "--icon=icon.ico",              # App icon
            "--add-data=icon.ico;.",         # Include icon for runtime
            "--add-data=logo.png;.",         # Include logo for runtime
            # Hidden imports for libraries that PyInstaller might miss
            "--hidden-import=customtkinter",
            "--hidden-import=PIL",
            "--hidden-import=PIL._tkinter_finder",
            "--hidden-import=cv2",
            "--hidden-import=numpy",
            "--hidden-import=packaging",
            "--hidden-import=packaging.version",
            "--hidden-import=tkinterdnd2",
            "--hidden-import=psd_tools",
            # Collect all customtkinter data files (themes, etc.)
            "--collect-all=customtkinter",
            "--collect-all=tkinterdnd2",
            # Main script
            "app.py"
        ]

    print()
    print("[*] Building... This may take a few minutes.")
    print()

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        if IS_MACOS:
            app_path = os.path.join("dist", "RZ Autometadata.app")
            if os.path.exists(app_path):
                print()
                print("=" * 60)
                print(f"  [OK] BUILD SUCCESSFUL!")
                print(f"  Output: {os.path.abspath(app_path)}")
                print("=" * 60)

                # Create DMG
                print()
                print("[*] Creating DMG installer...")
                _create_dmg()
            else:
                # Fallback: check for onedir output
                onedir = os.path.join("dist", "RZ Autometadata")
                if os.path.exists(onedir):
                    print(f"  Output: {os.path.abspath(onedir)}")
                else:
                    print("[!] Build finished but .app not found at expected path")
        else:
            exe_path = os.path.join("dist", "RZ Autometadata.exe")
            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                print()
                print("=" * 60)
                print(f"  [OK] BUILD SUCCESSFUL!")
                print(f"  Output: {os.path.abspath(exe_path)}")
                print(f"  Size: {size_mb:.1f} MB")
                print("=" * 60)
            else:
                print("[!] Build finished but exe not found at expected path")
    else:
        print()
        print("[FAIL] BUILD FAILED! Check the error messages above.")
        sys.exit(1)


def _create_dmg():
    """Create a DMG file from the built .app (macOS only)."""
    if not IS_MACOS:
        return

    app_path = os.path.join("dist", "RZ Autometadata.app")
    if not os.path.exists(app_path):
        print("[!] Cannot create DMG: .app not found")
        return

    # Read version from auto_updater
    try:
        from core.auto_updater import CURRENT_VERSION
        version = CURRENT_VERSION
    except ImportError:
        version = "1.0.0"

    dmg_name = f"RZ_Autometadata_v{version}_macOS.dmg"
    dmg_path = os.path.join("dist", dmg_name)

    # Remove old DMG if exists
    if os.path.exists(dmg_path):
        os.remove(dmg_path)

    # Create DMG using hdiutil (macOS built-in)
    cmd = [
        "hdiutil", "create",
        "-volname", "RZ Autometadata",
        "-srcfolder", app_path,
        "-ov",
        "-format", "UDZO",
        dmg_path
    ]

    result = subprocess.run(cmd)
    if result.returncode == 0 and os.path.exists(dmg_path):
        size_mb = os.path.getsize(dmg_path) / (1024 * 1024)
        print()
        print("=" * 60)
        print(f"  [OK] DMG CREATED!")
        print(f"  Output: {os.path.abspath(dmg_path)}")
        print(f"  Size: {size_mb:.1f} MB")
        print("=" * 60)
    else:
        print("[!] DMG creation failed")


if __name__ == "__main__":
    main()
