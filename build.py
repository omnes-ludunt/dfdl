#!/usr/bin/env python3

import platform
import subprocess
import sys
from pathlib import Path

def check_requirements():
    """Check if required packages for building are installed"""
    try:
        subprocess.run(["pyinstaller", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PyInstaller is required but not installed.")
        print("To install, run one of:")
        print("  pip install pyinstaller")
        print("  conda install pyinstaller")
        sys.exit(1)

def build_executable():
    """Build executable for current platform"""
    system = platform.system().lower()
    
    # Base PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=dfdl",
        "--clean",
        "--noconfirm",
    ]
    
    # Platform specific options
    if system == "darwin":  # macOS
        cmd.extend([
            "--windowed",  # Create .app bundle
            "--icon=apps/Dwarf Fortress.app/Contents/Resources/df.icns",
            "--target-architecture=universal2",  # Support both Intel and Apple Silicon
            "--osx-bundle-identifier=com.dfdl.app",
        ])
    elif system == "windows":
        cmd.extend([
            "--onefile",  # Only use onefile for Windows
            "--icon=apps/df.ico",
        ])
    
    # Add the main script
    cmd.append("dfdl.py")
    
    # Run PyInstaller
    subprocess.run(cmd, check=True)
    
    # Move the executable to the dist directory
    dist_dir = Path("dist")
    dist_dir.mkdir(exist_ok=True)
    
    if system == "darwin":
        # For macOS, we need to handle the .app bundle
        app_name = "dfdl.app"
        if (Path("dist") / app_name).exists():
            # Ensure the app has proper permissions
            subprocess.run(["chmod", "-R", "755", str(Path("dist") / app_name)], check=True)
            print(f"Created {app_name} in dist directory")
    else:
        # For Windows and Linux
        exe_name = "dfdl.exe" if system == "windows" else "dfdl"
        if (Path("dist") / exe_name).exists():
            print(f"Created {exe_name} in dist directory")

def main():
    print("Checking installation of build requirements...")
    check_requirements()
    
    print("\nBuilding executable...")
    build_executable()
    
    print("\nBuild complete! Check the 'dist' directory for your executable.")

if __name__ == "__main__":
    main()