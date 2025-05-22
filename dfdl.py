#!/usr/bin/env python3

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import subprocess
import time
import re
import gzip
import urllib.request
from pathlib import Path
from html.parser import HTMLParser
from abc import ABC, abstractmethod

# Define and collect input arguments
def parse_args():
    parser = argparse.ArgumentParser()
    
    # Optional arguments
    parser.add_argument('--gen_config', default=False, action='store_true',
                        help='A flag telling the script to generate or overwrite '+\
                            'the config.json file with a template, then exit.')
    parser.add_argument('--df_ver', default=None,
                        help='The version of Dwarf Fortress to install.'+\
                            ' If not specified, the version will be prompted.')
    parser.add_argument('--df_source', default=None,
                        help='The source of Dwarf Fortress to install.'+\
                            ' If not specified, the source will be prompted.')
    parser.add_argument('--auto_install', default=False, action='store_true',
                        help='A flag telling the script to automatically install '+\
                            'all packages based on the best estimate of compatibility, '+\
                            'without prompting for package choice or confirmation.')
    args = parser.parse_args()
    return args

class PackageHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr in attrs:
                if attr[0] == "href":
                    self.hrefs.append(attr[1])

class Version:
    def __init__(self, package_name, major=None, minor=None, patch=None, letter=None,
                 os_ver=None,arch=None):
        self.package_name = package_name
        self.major = major
        self.minor = minor
        self.patch = patch
        self.letter = letter
        self.os_ver = os_ver
        self.arch = arch
    
    def __str__(self):
        ver_str = f"{self.major}"   
        if self.minor is not None:
            ver_str += f".{self.minor}"
        if self.patch is not None:
            ver_str += f".{self.patch}"
        if self.letter is not None:
            ver_str += f"{self.letter}"
        if self.os_ver is not None:
            ver_str += f"_{self.os_ver}"
        if self.arch is not None:
            ver_str += f"-{self.arch}"
        return ver_str
    
    def __lt__(self, other):
        if not isinstance(other, Version):
            other = Version(str(other))

        # Handle None values by treating them as smaller than any number
        if self.major is None or other.major is None:
            return self.major is None and other.major is not None        
        if self.major != other.major:
            return self.major < other.major
        
        if self.minor is None or other.minor is None:
            return self.minor is None and other.minor is not None
        if self.minor != other.minor:
            return self.minor < other.minor
        
        if self.patch is None or other.patch is None:
            return self.patch is None and other.patch is not None
        if self.patch != other.patch:
            return self.patch < other.patch
        
        # Handle None letters by treating them as smaller than any letter
        if self.letter is None or other.letter is None:
            return self.letter is None and other.letter is not None
        return self.letter < other.letter
    
    def __eq__(self, other):
        if not isinstance(other, Version):
            other = Version(str(other))
        return (self.major == other.major and 
                self.minor == other.minor and 
                self.patch == other.patch and 
                self.letter == other.letter)
    
    def _check_version_compatibility(self, version):
        """Helper function to check compatibility with a single version"""
        if version.package_name == self.package_name:
            print(f"Warning: Checking compatibility between the same package:\n"+\
                f"{self.package_name} versions {self} and {version}")
            return False
        elif version.package_name == "Dwarf Fortress":
            if self.major != version.major or self.minor != version.minor:
                return False
        return True

    def is_compatible_with(self, installed_packages):
        """Check if this version is compatible with a set of others"""
        if installed_packages is None:
            return True
            
        if isinstance(installed_packages, dict):
            for _, version in installed_packages.items():
                if not self._check_version_compatibility(version):
                    return False
            return True
            
        elif isinstance(installed_packages, Version):
            return self._check_version_compatibility(installed_packages)
            
        else:
            print(f"Warning: Checking compatibility with {self.package_name} against {installed_packages},"+\
                  f"but installed packages must be a dictionary or Version object, not {type(installed_packages)}")
            return False

class Package:
    @classmethod
    def get_package_name(cls):
        """Get the package name. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement get_package_name classmethod")
    
    @property
    def package_name(self):
        """Instance property that calls the class method"""
        return self.get_package_name()
    
    def __init__(self, release_dir, cache_dir, os_ver, use_wine=False, required=False):
        self.release_dir = Path(release_dir)
        self.cache_dir = Path(cache_dir)
        self.os_ver = os_ver
        self.use_wine = use_wine
        self.required = required
        self.version = None
        self.dependencies = []

    def handle_network_error(self, e, operation):
        """Handle network-related errors with informative messages"""
        if isinstance(e, urllib.error.HTTPError):
            print(f"\nHTTP Error during {operation}: {e.code} - {e.reason}")
        elif isinstance(e, urllib.error.URLError):
            print(f"\nNetwork Error during {operation}: {e.reason}")
        else:
            print(f"\nUnexpected error during {operation}: {str(e)}")
        return False

    def filter_name(self, name):
        if not self.use_wine:
            os_rem = {
                # {'ver': '', 'rem': ['mac','osx','OSX','lin','Lin','win','Win','64','32']},
                'win32': ['mac','osx','OSX','lin','Lin','64'],
                'win64': ['mac','osx','OSX','lin','Lin'],
                'lin32': ['mac','osx','OSX','win','Win','64'],
                'lin64': ['mac','osx','OSX','win','Win'],
                'mac32': ['lin','Lin','win','Win','64'],
                'mac64': ['lin','Lin','win','Win']
            }
            wrong_match = False
            for rem in os_rem[self.os_ver]:
                wrong_match = wrong_match or rem in name
            return not wrong_match
        else:
            # If using Wine, allow Windows versions matching the architecture
            os_rem = {
                # {'ver': '', 'rem': ['mac','osx','OSX','lin','Lin','win','Win','64','32']},
                'win32': ['mac','osx','OSX','lin','Lin','64'],
                'win64': ['mac','osx','OSX','lin','Lin'],
                'lin32': ['mac','osx','OSX','lin','Lin','64'],
                'lin64': ['mac','osx','OSX','lin','Lin'],
                'mac32': ['mac','osx','OSX','lin','Lin','64'],
                'mac64': ['mac','osx','OSX','lin','Lin'],
            }
            wrong_match = False
            for rem in os_rem[self.os_ver]:
                wrong_match = wrong_match or rem in name
            return not wrong_match

    def match_name(self, name):
        return self.filter_name(name)
    
    def choose(self, installed_packages=None):
        try:
            file_list = self.get_list()
            num_options = len(file_list)
            if num_options == 0:
                if self.required:
                    raise ValueError("Failed to retrieve any matching versions, "+\
                                     "this package is required and cannot be skipped.")
                else:
                    print("Failed to retrieve any matching versions, continue without this package? (y/n)")
                    if input().lower().startswith('y'):
                        print(f"Skipping")
                        return False
                    else:
                        sys.exit(1)
            
            print("\nSelect a version from the following list, by inputting the corresponding number:")
            for i, n in enumerate(reversed(file_list), start=1):
                print(f"{len(file_list)-i+1})\t{n['name']}")
            if not self.required:
                print("0)\tSkip this package? Be careful of dependency between packages.")
            
            while True:
                index = input()
                if not str(index).isdigit():
                    print("Please enter a valid number")
                    continue
                index = int(index)
                if index == 0 and not self.required:
                    print(f"Skipping")
                    return False
                elif index < 1 or index > num_options:
                    print(f"Please enter a number between {1 if self.required else 0} and {num_options}")
                    continue
                else:
                    # Check compatibility
                    if not self.check_compatibility(installed_packages):
                        if input("Choose again? Otherwise, proceed with this version. (y/n): ").lower().startswith('y'):
                            continue
                    break
            
            choice = file_list[index-1]
            self.filename, self.url = choice['name'], choice['url']
            return True
            
        except Exception as e:
            if self.required:
                raise ValueError(f"Failed to process package: {str(e)}")
            print(f"\nError processing package: {str(e)}")
            print("Continue without this package? (y/n)")
            if input().lower().startswith('y'):
                return False
            sys.exit(1)

    def parse_version(self):
        """Default implementation for version parsing"""
        if hasattr(self, 'filename'):
            major = None
            minor = None
            patch = None
            letter = None
            os_ver = None
            arch = None

            partial_match = False
            
            # Try matching a format with patch number (e.g. df_40_24_03 or df_34_11_2a)
            match = re.search(r'(\d+)_(\d+)_(\d+)([a-z])?', self.filename)
            if match:
                partial_match = True
                major, minor, patch, letter = int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4)
            else:
                # Try matching a newer format with just major and minor version (e.g. df_50_05)
                match = re.search(r'(\d+)_(\d+)', self.filename)
                if match:
                    partial_match = True
                    major, minor = map(int, match.groups())
                else:
                    # If no match, try to extract any number as the major version
                    numbers = re.findall(r'\d+', self.filename)
                    if len(numbers) > 0:
                        major = int(numbers[0])
            
            # Extract OS and architecture
            os_patterns = {
                'win': r'win(?:dows)?(?:32|64)?',
                'mac': r'(?:mac|osx)(?:32|64)?',
                'lin': r'(?:lin|linux|deb|debian|ubuntu)(?:32|64)?'
            }
            
            for os_type, pattern in os_patterns.items():
                match = re.search(pattern, self.filename, re.IGNORECASE)
                if match:
                    if os_ver is not None and os_ver != os_type:
                        raise ValueError(f"OS version check failed, matching multiple options: "+\
                                         f"{os_ver} and {os_type} in filename {self.filename}")
                    os_ver = os_type
                    # Extract architecture if present
                    arch_match = re.search(r'(32|64)', match.group(0))
                    if arch_match:
                        arch = arch_match.group(1)
                    partial_match = True
            
            # Set the version if we have at least a partial match
            if partial_match:
                self.version = Version(
                    package_name=self.package_name,
                    major=major,
                    minor=minor,
                    patch=patch,
                    letter=letter,
                    os_ver=os_ver,
                    arch=arch
                )
        # At this point, we have a version, and correctly return None if no match
        return self.version
    
    def check_compatibility(self, installed_packages):
        """Check if this package is compatible with the given DF version"""
        if not self.version or not installed_packages or len(installed_packages) == 0:
            return True
        return self.version.is_compatible_with(installed_packages)
    
    def add_dependency(self, package_name, version_constraint=None):
        """Add a dependency to this package"""
        self.dependencies.append({
            'name': package_name,
            'version': version_constraint
        })
    
    def check_dependencies(self, installed_packages):
        """Check if all dependencies are satisfied"""
        no_missing_dependency = True
        for dep in self.dependencies:
            if dep['name'] not in installed_packages:
                print(f"\nWarning: Required dependency {dep['name']} is not installed")
                no_missing_dependency = False
            if dep['version']:
                installed_version = installed_packages[dep['name']]
                if not installed_version.is_compatible_with(dep['version']):
                    print(f"\nWarning: {dep['name']} version {installed_version} is not compatible with required version {dep['version']}")
                    no_missing_dependency = False
        return no_missing_dependency

    def download(self):
        cache_file = self.cache_dir / self.filename
        if not cache_file.exists():
            try:
                with urllib.request.urlopen(self.url, timeout=30) as response:
                    if response.status != 200:
                        raise urllib.error.HTTPError(
                            self.url, response.status, 
                            f"HTTP Error {response.status}", 
                            response.headers, None
                        )
                    with open(cache_file, 'wb') as out_file:
                        shutil.copyfileobj(response, out_file)
                return True
            except urllib.error.HTTPError as e:
                return self.handle_network_error(e, "download")
            except urllib.error.URLError as e:
                return self.handle_network_error(e, "download")
            except Exception as e:
                print(f"\nUnexpected error during download: {str(e)}")
                return False
        return True

    def extract(self):
        self.unpack(self.cache_dir / self.filename, self.release_dir)

    def run(self, installed_packages=None):
        if self.choose(installed_packages):
            self.parse_version()
            self.download()
            self.extract()
            return True
        return False

    def unpack(self, src, dest):
        shutil.unpack_archive(src, dest)

    def merge_dirs(self, source, target, overwrite=False):
        source = Path(source)
        target = Path(target)
        if not target.exists():
            target.mkdir(parents=True)
        for item in source.iterdir():
            target_item = target / item.name
            if item.is_dir():
                self.merge_dirs(item, target_item)
            else:
                if target_item.exists():
                    if overwrite:
                        shutil.copy2(item, target_item)
                else:
                    shutil.copy2(item, target_item)

class BitBucketPackage(Package):
    def get_list(self):
        with urllib.request.urlopen(self.releases_url) as response:
            data = json.load(response)
        return [
            {'name': a['name'], 'url': a['links']['self']['href']}
            for a in data['values'] if self.match_name(a['name'])
        ]

class GitHubPackage(Package):
    def get_list(self):
        page = 1
        assets = []
        while True:
            # Construct the URL with pagination parameters
            page_url = f"{self.releases_url}?page={page}&per_page=100"
            request = urllib.request.Request(page_url)
            if 'config' in globals():
                gh_token = config["github_token"]
                request.add_header("Authorization", f"Bearer {gh_token}")
            response = urllib.request.urlopen(request)
            if response.status == 200:
                data = json.loads(response.read())
                current_assets = [a for r in data for a in r.get('assets', []) if self.match_name(a.get('name', ''))]
                assets.extend(current_assets)
                
                # Check if there are more pages to fetch
                if len(current_assets) < 100:  # 100 releases per page from "&per_page=100"
                    break
                else:
                    page += 1
            else:
                if len(assets) == 0:
                    print("Failed to fetch data from GitHub API")
                    return []
            
        return [{'name': a.get('name', ''), 'url': a.get('browser_download_url', '')} for a in assets]
    
    def download(self):
        cache_file = self.cache_dir / self.filename
        if not cache_file.exists():
            request = urllib.request.Request(self.url)
            if 'config' in globals():
                gh_token = config["github_token"]
                request.add_header("Authorization", f"Bearer {gh_token}")
            with urllib.request.urlopen(request) as response, open(cache_file, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

class PyLNPPackage(GitHubPackage):
    @classmethod
    def get_package_name(cls):
        return "PyLNP"

    @property
    def releases_url(self):
        return "https://api.github.com/repos/Pidgeot/python-lnp/releases"

    def extract(self):
        if self.os_ver in ['mac32','mac64']:
            subprocess.run(["ditto", "-xk", f"{self.cache_dir}/{self.filename}", self.release_dir])
        else:
            self.unpack(f"{self.cache_dir}/{self.filename}", self.release_dir)

class DFPackage(Package, ABC):
    """Abstract base class for Dwarf Fortress package implementations."""
    
    @classmethod
    def get_package_name(cls):
        return "Dwarf Fortress"
    
    @abstractmethod
    def get_list(self):
        """Get list of available versions. Must be implemented by subclasses."""
        pass
    
    def match_name(self, name):
        os_in = {
            'win32': 'zip',
            'win64': 'zip',
            'lin32': 'linux',
            'lin64': 'linux',
            'mac32': 'osx',
            'mac64': 'osx'
        }
        # If using Wine, use Windows versions
        if self.use_wine:
            for ver in ['lin32', 'lin64', 'mac32', 'mac64']:
                os_in[ver] = 'zip'
        return self.filter_name(name) and os_in[self.os_ver] in name
    
    def extract(self):
        # Create df directory if it doesn't exist
        target_df_dir = self.release_dir / "df"
        target_df_dir.mkdir(exist_ok=True)
        
        # For Windows versions, the files are directly in the root
        if self.os_ver.startswith('win') or self.use_wine:
            self.unpack(self.cache_dir / self.filename, target_df_dir)
        else:
            self.unpack(self.cache_dir / self.filename, self.release_dir)
            # For other platforms, look for the df directory
            df_dir = [name for name in os.listdir(self.release_dir) if 'df' in name]
            if len(df_dir) != 1:
                if len(df_dir) > 1:
                    raise ValueError('Unexpected behavior, more than one path identified as an unpacked df folder:\n'+
                                 str(df_dir)+' selected from '+str(os.listdir(self.release_dir)))
                else:
                    raise ValueError('Unexpected behavior, no path identified as an unpacked df folder after extraction:\n'+
                                 str(df_dir)+' selected from '+str(os.listdir(self.release_dir)))
            shutil.move(self.release_dir / df_dir[0], target_df_dir)
        
        # Ensure Windows executables are executable for Wine users
        if self.use_wine:
            for exe in ['dfhack.exe', 'Dwarf Fortress.exe']:
                exe_path = self.release_dir / "df" / exe
                if exe_path.exists():
                    os.chmod(exe_path, 0o755)

class DFBay12(DFPackage):
    def get_list(self):
        with urllib.request.urlopen("http://bay12games.com/dwarves/older_versions.html") as response:
            # Check if the response is gzipped
            if response.info().get('Content-Encoding') == 'gzip':
                content = gzip.decompress(response.read()).decode('utf-8')
            else:
                content = response.read().decode('utf-8')
            parser = PackageHTMLParser()
            parser.feed(content)
        return [{'name': href, 'url': f"http://bay12games.com/dwarves/{href}"} for href in parser.hrefs if self.match_name(href)]

class ItchPackage(Package, ABC):
    """Abstract base class for packages downloaded from itch.io using butler."""
    
    # @classmethod
    # @abstractmethod
    # def get_itch_game_id(cls):
    #     """Get the itch.io game ID. Must be implemented by subclasses."""
    #     raise NotImplementedError("Subclasses must implement get_itch_game_id classmethod")
    
    # def __init__(self, release_dir, cache_dir, os_ver, use_wine=False, required=False):
    #     super().__init__(release_dir, cache_dir, os_ver, use_wine, required)
    #     self.butler_path = self._setup_butler()
    
    # def _check_butler_installed(self):
    #     """Check if butler is installed in PATH or common locations."""
    #     # First check if butler is in PATH
    #     butler = shutil.which('butler')
    #     if butler:
    #         return butler
            
    #     # Check recommended platform-specific locations first
    #     system = platform.system()
    #     recommended_paths = {
    #         'Darwin': [
    #             Path('/usr/local/bin/butler'),      # Intel Macs
    #             Path('/opt/homebrew/bin/butler'),   # Apple Silicon Macs
    #             Path.home() / '.local' / 'bin' / 'butler',  # User-specific
    #         ],
    #         'Linux': [
    #             Path.home() / '.local' / 'bin' / 'butler',  # Primary recommended
    #             Path('/usr/local/bin/butler'),             # Secondary recommended
    #             Path.home() / 'bin' / 'butler',            # Legacy location
    #         ],
    #         'Windows': [
    #             Path.home() / 'AppData' / 'Local' / 'butler' / 'butler.exe',  # Primary recommended
    #         ]
    #     }
        
    #     # Check itch app locations as fallback (managed by itch app)
    #     itch_paths = {
    #         'Darwin': Path.home() / "Library/Application Support/itch/apps/butler/butler",
    #         'Linux': Path.home() / ".config/itch/apps/butler/butler",
    #         'Windows': Path.home() / "AppData/Roaming/itch/apps/butler/butler.exe"
    #     }
        
    #     # Check recommended paths first
    #     if system in recommended_paths:
    #         for path in recommended_paths[system]:
    #             if path.exists():
    #                 return str(path)
        
    #     # Then check itch app paths
    #     if system in itch_paths and itch_paths[system].exists():
    #         return str(itch_paths[system])
        
    #     return None

    # def _suggest_installation(self):
    #     """Suggest butler installation methods to the user."""
    #     print("\nButler is required to download games from itch.io via command.")
    #     print("\nSee https://itch.io/docs/butler/ for more information.")
    #     print("\nYou have three options for installing butler:")
    #     print("1) Download and install the itch.io app (recommended)")
    #     print("   This will keep butler up-to-date automatically")
    #     print("   Visit: https://itch.io/app")
    #     print("\n2) Direct download of butler")
    #     print("   Manual installation, requires setting up PATH")
    #     print("   Visit: https://itchio.itch.io/butler")
    #     print("\n3) Let this script download and install butler automatically")
        
    #     choice = input("\nWould you like this script to install butler for you? (y/n)\n")
    #     if choice.lower().startswith('y'):
    #         return self._install_butler_automated()
    #     else:
    #         print("\nCannot proceed without butler. Please install butler manually and run this script again.")
    #         sys.exit(1)

    # def _install_butler_automated(self):
    #     """Install butler automatically using the automation-friendly method."""
    #     try:
    #         # Determine platform-specific download URL and binary name
    #         system = platform.system()
    #         machine = platform.machine().lower()
            
    #         # Check for supported architecture
    #         if not ('x86_64' in machine or 'amd64' in machine):
    #             raise ValueError(f"Unsupported CPU architecture: {machine}. Butler requires x86_64/amd64.")
            
    #         # Always download to Downloads folder first
    #         downloads_dir = Path.home() / 'Downloads'
    #         if not downloads_dir.exists():
    #             downloads_dir = Path.home()  # Fallback to home directory if Downloads doesn't exist
            
    #         # Determine platform-specific paths and info
    #         if system == 'Darwin':  # macOS
    #             # # Install to system directories only if user explicitly wants it
    #             # print("\nWould you like to install butler system-wide? This will require sudo privileges.")
    #             # print("Otherwise, it will be installed in your home directory.")
    #             # if input("Install system-wide? (y/n): ").lower().startswith('y'):
    #             #     install_dir = Path('/usr/local/bin')
    #             # else:
    #             #     install_dir = Path.home() / '.local' / 'bin'
    #             install_dir = Path('/usr/local/bin')
    #             platform_info = {'channel': 'darwin-amd64', 'binary': 'butler'}
    #         elif system == 'Linux':
    #             install_dir = Path.home() / '.local' / 'bin'
    #             platform_info = {'channel': 'linux-amd64', 'binary': 'butler'}
    #         elif system == 'Windows':
    #             install_dir = Path.home() / 'AppData' / 'Local' / 'butler'
    #             platform_info = {'channel': 'windows-amd64', 'binary': 'butler.exe'}
    #         else:
    #             raise ValueError(f"Unsupported operating system: {system}")
            
    #         # Create installation directory
    #         install_dir.mkdir(parents=True, exist_ok=True)
    #         print(f"Will install butler binary to: {install_dir}")
            
    #         # Download to Downloads directory first
    #         print(f"\nDownloading butler to {downloads_dir}...")
    #         url = f"https://broth.itch.ovh/butler/{platform_info['channel']}/LATEST/archive/default"
            
    #         butler_path = downloads_dir / platform_info['binary']
    #         butler_zip = downloads_dir / "butler.zip"
    #         butler_7z = downloads_dir / "7z.so"
    #         butler_7_lib = downloads_dir / "libc7zip.dylib"
            
    #         # Set up request with proper headers
    #         headers = {
    #             'User-Agent': 'dfdl/1.0',
    #             'Accept': '*/*'
    #         }
    #         request = urllib.request.Request(url, headers=headers)
            
    #         # Download with progress indication
    #         with urllib.request.urlopen(request) as response, open(butler_zip, 'wb') as out_file:
    #             total_size = int(response.headers['Content-Length'])
    #             downloaded = 0
    #             block_size = 8192
                
    #             while True:
    #                 buffer = response.read(block_size)
    #                 if not buffer:
    #                     break
    #                 downloaded += len(buffer)
    #                 out_file.write(buffer)
    #                 done = int(50 * downloaded / total_size)
    #                 sys.stdout.write(f"\r[{'=' * done}{' ' * (50-done)}] {downloaded}/{total_size} bytes")
    #                 sys.stdout.flush()
    #         print("\n")
            
    #         print("Extracting butler...")
    #         shutil.unpack_archive(butler_zip, downloads_dir)
            
    #         # Make butler executable
    #         if system != 'Windows':
    #             os.chmod(butler_path, 0o755)
            
    #         # Move to final location
    #         final_path = install_dir / platform_info['binary']
    #         shutil.move(butler_path, final_path)
    #         # if not str(install_dir).startswith(str(Path.home())):
    #         #     # Need sudo for system directories
    #         #     print(f"\nMoving butler to {install_dir} (requires sudo)...")
    #         #     result = subprocess.run(['sudo', 'install', '-m', '755', str(butler_path), str(final_path)], capture_output=True, text=True)
    #         #     if result.returncode != 0:
    #         #         raise RuntimeError(f"Failed to install butler: {result.stderr}")
    #         # else:
    #         #     # User directory, just move normally
    #         #     shutil.move(butler_path, final_path)
            
    #         # Clean up
    #         butler_zip.unlink()
    #         butler_7z.unlink()
    #         butler_7_lib.unlink()


    #         print("\nButler installed successfully!")

    #         # Add to PATH instructions
    #         self._print_path_instructions(install_dir, system)
    #         return str(final_path)
            
    #     except Exception as e:
    #         print(f"\nFailed to install butler: {str(e)}")
    #         print("Please install butler manually, see instructions at https://itch.io/docs/butler/")
    #         sys.exit(1)

    # def _print_path_instructions(self, install_dir, system):
    #     """Print instructions for adding butler to PATH."""
    #     print("\nTo add butler to your PATH permanently:")
        
    #     if system == 'Windows':
    #         print("1. Open System Properties > Advanced > Environment Variables")
    #         print("2. Under 'User variables', find and edit 'Path'")
    #         print(f"3. Add this directory: {install_dir}")
            
    #     elif system == 'Darwin':  # macOS
    #         if install_dir in [Path('/usr/local/bin'), Path('/opt/homebrew/bin')]:
    #             print("No PATH configuration needed - this location is already in your PATH")
    #         else:
    #             shell = os.environ.get('SHELL', '').lower()
    #             if 'zsh' in shell:
    #                 config_file = '~/.zshrc'
    #             else:
    #                 config_file = '~/.bash_profile'
    #             print(f"1. Open or create {config_file} in a text editor")
    #             print(f"2. Add this line: export PATH=\"{install_dir}:$PATH\"")
    #             print(f"3. Restart your terminal or run: source {config_file}")
            
    #     else:  # Linux
    #         if install_dir == Path('/usr/local/bin'):
    #             print("No PATH configuration needed - this location is already in your PATH")
    #         else:
    #             print("1. Open or create ~/.bashrc in a text editor")
    #             print(f"2. Add this line: export PATH=\"{install_dir}:$PATH\"")
    #             print("3. Restart your terminal or run: source ~/.bashrc")
    
    # def _setup_butler(self):
    #     """Check for butler and handle installation if needed."""
    #     butler_path = self._check_butler_installed()
    #     if not butler_path:
    #         butler_path = self._suggest_installation()
        
    #     # Verify butler works
    #     try:
    #         result = subprocess.run([butler_path, '-V'], 
    #                              capture_output=True, text=True)
    #         if result.returncode != 0:
    #             raise RuntimeError("Butler verification failed")
    #         print(f"Using butler: {result.stdout.strip()}")
    #         return butler_path
    #     except Exception as e:
    #         print(f"\nError verifying butler installation: {str(e)}")
    #         print("Please ensure butler is properly installed: https://itch.io/docs/butler/")
    #         sys.exit(1)
    
    # def _get_channel_name(self):
    #     """Get the appropriate channel name based on OS and architecture."""
    #     if self.use_wine:
    #         return "windows"
    #     elif self.os_ver.startswith('win'):
    #         return "windows"
    #     elif self.os_ver.startswith('mac'):
    #         return "osx"
    #     elif self.os_ver.startswith('lin'):
    #         return "linux"
    #     else:
    #         raise ValueError(f"Unsupported OS version: {self.os_ver}")
    
    def get_list(self):
        """Get list of available downloads from user's itch.io library."""
        try:
            if 'itch_key' not in config:
                raise ValueError("No itch.io API key found in config.json. Please generate the file with --gen_config and add your API key."+\
                               "\nTo get your itch.io API key:"+\
                               "\n1. Go to https://itch.io/user/settings/api-keys"+\
                               "\n2. Generate a new API key"+\
                               "\n3. Copy it to the config.json file")

            # Common headers for all requests
            headers = {
                'Authorization': f'Bearer {config["itch_key"]}',
                'User-Agent': 'dfdl/1.0'
            }


            # Get the user's profile
            library_url = f"https://itch.io/api/1/key/me"
            request = urllib.request.Request(library_url, headers=headers)
            
            print(f"Requesting profile from: {library_url}")
            with urllib.request.urlopen(request) as response:
                user_data = json.loads(response.read())
                print(f"Processing json response:\n{user_data}")
                if 'errors' in user_data:
                    raise ValueError(f"API Error: {user_data['errors']}")
            
            # Get the user's owned games
            library_url = f"https://api.itch.io/profile/owned-keys"
            request = urllib.request.Request(library_url, headers=headers)
            
            print(f"Requesting games list from: {library_url}")
            with urllib.request.urlopen(request) as response:
                purchased_keys = json.loads(response.read())
                print(f"Processing json response:\n{purchased_keys}")
                if 'errors' in purchased_keys:
                    raise ValueError(f"API Error: {purchased_keys['errors']}")
                
            # Parse out game info from owned_keys
            games = []
            for key_data in purchased_keys.get('owned_keys', []):
                game_data = key_data.get('game', {})
                games.append({
                    'title': game_data.get('title'),
                    'game_id': key_data.get('game_id'),
                    'url': game_data.get('url'),
                    'download_key_id': key_data.get('id')
                })
            
            # Print found games for debugging
            print("\nFound games:")
            # Find Dwarf Fortress in the owned keys
            df_key = None
            for game in games:
                print(f"- {game['title']}: ID {game['game_id']}, URL: {game['url']}, Download Key ID: {game['download_key_id']}")
                if game.get('title', '').lower() == 'dwarf fortress':
                    df_key = game['id']
                    game_id = game['game_id']
                    print(f"Found Dwarf Fortress with key: {df_key} and game ID: {game_id}")
            if not df_key:
                raise ValueError("Dwarf Fortress not found in your itch.io library. Have you purchased it?")
            
            # Get the download list for this key
            downloads_url = f"https://itch.io/api/1/jwt/download-key/{df_key}/download-sessions"
            request = urllib.request.Request(downloads_url, headers=headers)
            
            print(f"Requesting download list from: {downloads_url}")
            with urllib.request.urlopen(request) as response:
                downloads = json.loads(response.read())
                print(f"Processing json response:\n{downloads}")
                if 'errors' in downloads:
                    raise ValueError(f"API Error: {downloads['errors']}")
                
            # Filter downloads based on OS
            os_type = self._get_os_type()
            matching_downloads = []
            for download in downloads:
                platform = download.get('platform', '').lower()
                if os_type in platform or 'all' in platform:
                    matching_downloads.append(download)
            
            if not matching_downloads:
                raise ValueError(f"No downloads found for {os_type} in your itch.io library")
                
            return [{'name': d['filename'], 'url': d['url']} for d in matching_downloads]
            
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("Error: Invalid or missing itch.io API key. Please check your config.json")
                sys.exit(1)
            elif e.code == 403:
                print("Error: You don't have permission to access this game. "+\
                      "Have you purchased it? Have you set the correct itch.io API key in config.json?")
                sys.exit(1)
            else:
                print(f"HTTP Error getting download list: {e}")
                print("\nThis could be because:")
                print("1. Your itch.io API key is incorrect")
                print("2. You haven't purchased Dwarf Fortress on itch.io")
                print("3. The itch.io API is temporarily unavailable")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting download list: {str(e)}")
            sys.exit(1)

    def _get_os_type(self):
        """Get the OS type for filtering downloads."""
        if self.use_wine:
            return "windows"
        elif self.os_ver.startswith('win'):
            return "windows" 
        elif self.os_ver.startswith('mac'):
            return "osx"
        elif self.os_ver.startswith('lin'):
            return "linux"
        else:
            raise ValueError(f"Unsupported OS version: {self.os_ver}")

    def download(self):
        """Download the selected version using butler."""
        try:
            # Create a temporary directory for butler to download to
            temp_dir = self.cache_dir / "butler_temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Run butler to download the selected channel
            result = subprocess.run(
                [self.butler_path, 'fetch', self.get_itch_game_id(), self.filename, str(temp_dir)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Butler download failed: {result.stderr}")
                
            # Move downloaded files to cache directory
            for item in temp_dir.iterdir():
                shutil.move(item, self.cache_dir / item.name)
                
            # Clean up temp directory
            shutil.rmtree(temp_dir)
            
            return True
            
        except Exception as e:
            print(f"Error downloading version: {str(e)}")
            return False

class DFItch(ItchPackage, DFPackage):
    """Dwarf Fortress package from itch.io using butler for downloads."""
    
    @classmethod
    def get_itch_game_id(cls):
        return "dwarf-fortress"
    
    def __init__(self, release_dir, cache_dir, os_ver, use_wine=False, required=False):
        # Use super() to properly handle the diamond inheritance
        super().__init__(release_dir, cache_dir, os_ver, use_wine, required)
    
    # def get_list(self):
    #     """Get list of available versions using butler."""
    #     try:
    #         # Run butler to list available channels
    #         result = subprocess.run(
    #             [self.butler_path, 'channel', 'list', self.get_itch_game_id()],
    #             capture_output=True,
    #             text=True
    #         )
            
    #         if result.returncode != 0:
    #             raise RuntimeError(f"Butler command failed: {result.stderr}")
                
    #         # Parse channel list
    #         channels = []
    #         for line in result.stdout.split('\n'):
    #             if line.strip():
    #                 channels.append(line.strip())
            
    #         # Filter channels based on OS
    #         channel_name = self._get_channel_name()
    #         matching_channels = [c for c in channels if channel_name in c.lower()]
            
    #         if not matching_channels:
    #             raise ValueError(f"No matching channels found for {channel_name}")
                
    #         return [{'name': c, 'url': c} for c in matching_channels]
            
    #     except Exception as e:
    #         print(f"Error getting version list: {str(e)}")
    #         return []

class DFHackPackage(GitHubPackage):
    @classmethod
    def get_package_name(cls):
        return "DFHack"

    def match_name(self, name):
        os_in = {
            'win32': 'Windows',
            'win64': 'Windows',
            'lin32': 'Linux',
            'lin64': 'Linux',
            'mac32': 'OSX-32',
            'mac64': 'OSX-64'
        }
        # If using Wine, use Windows versions
        if self.use_wine:
            for ver in ['lin32', 'lin64', 'mac32', 'mac64']:
                os_in[ver] = 'Windows'
        return self.filter_name(name) and os_in[self.os_ver] in name

    @property
    def releases_url(self):
        return "https://api.github.com/repos/DFHack/dfhack/releases"

    def extract(self):
        self.unpack(self.cache_dir / self.filename, self.release_dir / "df")
        # Ensure DFHack executables are executable
        if self.os_ver in ['mac32', 'mac64', 'lin32', 'lin64']:
            for exe in ['dfhack', 'dfhack-run']:
                exe_path = self.release_dir / "df" / exe
                if exe_path.exists():
                    os.chmod(exe_path, 0o755)

class RubyPackage(Package):
    @classmethod
    def get_package_name(cls):
        return "Ruby"
    
    def match_name(self, name):
        os_in = {
            'win32': 'zip',
            'win64': 'zip',
            'lin32': 'linux',
            'lin64': 'linux',
            'mac32': 'osx',
            'mac64': 'osx'
        }
        # If using Wine, use Windows versions
        if self.use_wine:
            for ver in ['lin32', 'lin64', 'mac32', 'mac64']:
                os_in[ver] = 'zip'
        return self.filter_name(name) and os_in[self.os_ver] in name
    
    def get_list(self):
        if self.os_ver in ['mac64']:
            return [{'name':"ruby-2.7.5.tar.bz2", 
                    'url':"https://s3.amazonaws.com/travis-rubies/binaries/osx/10.13/x86_64/ruby-2.7.5.tar.bz2"}]
    
    def extract(self):
        self.unpack(self.cache_dir / self.filename, self.release_dir)
        shutil.move(self.release_dir / "ruby-2.7.5" / "lib" / "libruby.2.7.dylib", 
                   self.release_dir / "df" / "hack" / "libruby.dylib")
        for file_path in Path(self.release_dir / "ruby-2.7.5").glob("*"):
            if file_path.is_file():
                file_path.unlink()
        shutil.rmtree(self.release_dir / "ruby-2.7.5")

class DwarfTherapistPackage(GitHubPackage):
    @classmethod
    def get_package_name(cls):
        return "Dwarf Therapist"
    
    def match_name(self, name):
        os_in = {
            'win32': 'win',
            'win64': 'win',
            'lin32': 'linux',
            'lin64': 'linux',
            'mac32': 'osx',
            'mac64': 'osx'
        }
        # If using Wine, use Windows versions
        if self.use_wine:
            for ver in ['lin32', 'lin64', 'mac32', 'mac64']:
                os_in[ver] = 'win'
        return self.filter_name(name) and os_in[self.os_ver] in name

    @property
    def releases_url(self):
        return "https://api.github.com/repos/Dwarf-Therapist/Dwarf-Therapist/releases"

    def extract(self):
        if self.os_ver in ['mac32','mac64']:
            subprocess.run(["hdiutil","attach", str(self.cache_dir / self.filename)])
            subprocess.run(["ditto", "-xk", f"/Volumes/{Path(self.filename).stem}", 
                          str(self.release_dir / "LNP" / "utilities")])
            subprocess.run(["hdiutil","detach", f"/Volumes/{Path(self.filename).stem}"])
        elif self.os_ver in ['lin32','lin64']:
            self.unpack(self.cache_dir / self.filename, self.release_dir / "LNP" / "utilities")
        elif self.os_ver in ['win32','win64']:
            self.unpack(self.cache_dir / self.filename, self.release_dir / "LNP" / "utilities")

class TWBTPackage(GitHubPackage):
    @classmethod
    def get_package_name(cls):
        return "TWBT"

    @property
    def releases_url(self):
        return "https://api.github.com/repos/thurin/df-twbt/releases"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_dependency('DFHack')

    def extract(self):
        self.unpack(self.cache_dir / self.filename, self.release_dir / "twbt")
        twbt_dirs = [name for name in os.listdir(self.release_dir / "twbt") 
                     if (self.release_dir / "twbt" / name).is_dir() 
                     and not name.startswith("_") and not name.startswith(".")]
        if len(twbt_dirs) != 1:
            raise ValueError('Could not uniquely identify twbt plugin folder from:\n'+str(twbt_dirs))
        else:
            for file_path in Path(self.release_dir / "twbt" / twbt_dirs[0]).glob("*"):
                shutil.move(file_path, self.release_dir / "df" / "hack" / "plugins")
            shutil.rmtree(self.release_dir / "twbt" / twbt_dirs[0])
        for ext in ['png', 'lua']:
            for file_path in Path(self.release_dir / "twbt").glob(f"*.{ext}"):
                if ext == 'lua':
                    shutil.move(file_path, self.release_dir / "df" / "hack" / "lua")
                elif ext == 'png':
                    art_file = self.release_dir / "df" / "data" / "art" / file_path.name
                    if art_file.exists():
                        art_file.unlink()
                    shutil.move(file_path, self.release_dir / "df" / "data" / "art")
        overrides_file = self.release_dir / "df" / "data" / "init" / "overrides.txt"
        if overrides_file.exists():
            overrides_file.unlink()
        shutil.move(self.release_dir / "twbt" / "overrides.txt", self.release_dir / "df" / "data" / "init")
        shutil.rmtree(self.release_dir / "twbt")

class SoundsensePackage(Package):    
    @classmethod
    def get_package_name(cls):
        return "Soundsense"
    
    def match_name(self, name):
        return 'zip' in name and 'soundpack' not in name
    
    @property
    def releases_url(self):
        return "https://df.zweistein.cz/soundsense/"
    
    def get_list(self):
        with urllib.request.urlopen("https://df.zweistein.cz/soundsense/") as response:
            parser = PackageHTMLParser()
            parser.feed(response.read().decode())
        return [{'name': href, 'url': f"https://df.zweistein.cz/soundsense/{href}"} for href in parser.hrefs if self.match_name(href)]
    
    # https://df.zweistein.cz/soundsense/soundpack.zip
    
    # def extract(self):
    #     self.unpack(f"{self.cache_dir}/{self.filename}", f"{self.release_dir}")
    #     input(f"\nContinue? (y/n)\n")
    #     shutil.move(f"{self.release_dir}/ruby-2.7.5/lib/libruby.2.7.dylib", f"{self.release_dir}/df/hack/libruby.dylib")
    #     for file_path in Path(self.release_dir, "ruby-2.7.5").glob("*"):
    #         if file_path.is_file():
    #             os.remove(file_path)
    #     shutil.rmtree(f"{self.release_dir}/ruby-2.7.5")

class PEStarterPackPackage(Package):    
    @classmethod
    def get_package_name(cls):
        return "PE Starter Pack"

    def get_list(self):
        with urllib.request.urlopen("http://df.wicked-code.com") as response:
            # Check if the response is gzipped
            if response.info().get('Content-Encoding') == 'gzip':
                content = gzip.decompress(response.read()).decode('utf-8')
            else:
                content = response.read().decode('utf-8')
            parser = PackageHTMLParser()
            parser.feed(content)
        return [{'name': href, 'url': f"http://df.wicked-code.com/{href}"} for href in reversed(parser.hrefs) if 'zip' in href]
    
    def extract(self):
        self.unpack(self.cache_dir / self.filename, self.release_dir / "PESP")
        for folder in ['colors','defaults','embarks','graphics','keybinds','tilesets']:
            self.merge_dirs(self.release_dir / "PESP" / "LNP" / folder,
                          self.release_dir / "LNP" / folder)
        for file_path in Path(self.release_dir / "PESP").glob("*"):
            if file_path.is_file():
                file_path.unlink()
        shutil.rmtree(self.release_dir / "PESP")

class LMPPackage(Package):
    @classmethod
    def get_package_name(cls):
        return "LMP"

    def get_list(self):
        if self.os_ver in ['mac64']:
            return [
                {'name':"Lazy Mac Pack v0.47.05 dfhack-r1.dmg",
                 'url':"https://dffd.bay12games.com/download.php?id=12202&f=Lazy+Mac+Pack+v0.47.05+dfhack-r1.dmg"},
                {'name':"Lite Lazy Mac Pack v0.47.04.dmg",
                 'url':"https://dffd.bay12games.com/download.php?id=12310&f=Lazy+Mac+Pack+v0.47.04.dmg"},
                {'name':"Mac OS X 10.6-10.8 Lazy Mac Pack v0.44.09-32.dmg",
                 'url':"https://dffd.bay12games.com/download.php?id=12061&f=Lazy+Mac+Pack+v0.44.09-32.dmg"},
                {'name':"Mac OS X 10.5 Dwarf Fortress SSTM Pack v0.44.02.dmg",
                 'url':"https://dffd.bay12games.com/download.php?id=12093&f=Dwarf+Fortress+SSTM+Pack+v0.44.02.dmg"},
            ]    

    def extract(self):
        if self.os_ver in ['mac32','mac64']:
            subprocess.run(["hdiutil","attach", str(self.cache_dir / self.filename)])
            lmp_dir = [name for name in os.listdir(f"/Volumes/{Path(self.filename).stem}")
                       if 'App' not in name and '.DS' not in name]
            if len(lmp_dir) != 1:
                if len(lmp_dir) > 1:
                    raise ValueError('Unexpected behavior, more than one path identified as an LMP folder:\n'+
                                    str(lmp_dir)+' selected from '+str(os.listdir(f"/Volumes/{Path(self.filename).stem}")))
                else:
                    raise ValueError('Unexpected behavior, no path identified as an LMP folder after mounting the .dmg:\n'+
                                    str(lmp_dir)+' selected from '+str(os.listdir(f"/Volumes/{Path(self.filename).stem}")))
            subprocess.run(["ditto", f"/Volumes/{Path(self.filename).stem}/{lmp_dir[0]}", 
                          str(self.release_dir / "LMP")])
            subprocess.run(["hdiutil","detach", f"/Volumes/{Path(self.filename).stem}"])
            shutil.move(self.release_dir / "LMP" / "LNP", self.release_dir / "LNP")
            for file_path in Path(self.release_dir / "LMP").glob("*"):
                if file_path.is_file():
                    file_path.unlink()
            shutil.rmtree(self.release_dir / "LMP")

# For managing github tokens, as a module method
class Config:
    @staticmethod
    def load():
        with open("config.json", "r") as f:
            return json.load(f)

class Release:
    def __init__(self):
        # Parse arguments
        args = parse_args()
        if args.gen_config:
            with open("config.json","w") as cfg:
                cfg.write("{\n    \"github_token\": \"your_github_token_here\",\n    \"itch_key\": \"your_itch_api_key_here\"\n}\n")
            print("\nA config template has been generated at config.json")
            print("Please edit it to add your:")
            print("1. GitHub token (for accessing GitHub releases)")
            print("2. itch.io API key (for downloading from itch.io)")
            print("\nTo get your itch.io API key:")
            print("1. Go to https://itch.io/user/settings/api-keys")
            print("2. Generate a new API key")
            print("3. Copy it to the config.json file")
            exit(1)
        # Start a log file with timestamp
        self.log = f"Build started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        self.log += f"System: {platform.system()} {platform.release()}\n"
        self.log += f"Python: {sys.version}\n\n"
        
        # Set version and os variables
        self.os_ver = self.check_os()
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.release_dir = Path(self.temp_dir_obj.name)
        print(f"\nPreparing a temporary directory at {self.release_dir}")
        self.cache_dir = Path("package_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_wine = self.check_wine()
        self.target_dir = self.check_target_dir()
        self.tileset_dir = Path("tilesets")
        if Path("config.json").exists():
            global config
            config = Config.load()
        
    def check_os(self):
        os_ver = {
            'Windows (32-bit)' : 'win32',
            'Windows (64-bit)' : 'win64',
            'Linux (32-bit)' : 'lin32',
            'Linux (64-bit)' : 'lin64',
            'Mac (32-bit)' : 'mac32',
            'Mac (64-bit)' : 'mac64'
        }
        os_match = {
            'Windows':['Windows (32-bit)','Windows (64-bit)'],
            'Linux':['Linux (32-bit)','Linux (64-bit)'],
            'Darwin':['Mac (32-bit)','Mac (64-bit)']
        }
        detected_os = os_match[platform.system()][sys.maxsize > 2**32]
        choice = input(f"\nSystem detected as '{detected_os}'. Is this correct? (y/n)\n")
        if choice.lower().startswith('y'):
            return os_ver[detected_os]
        else:
            print("\nSelect your OS, by inputting the corresponding number:")
            os_list = [
                'Windows (32-bit)',
                'Windows (64-bit)',
                'Linux (32-bit)',
                'Linux (64-bit)', 
                'Mac (32-bit)',
                'Mac (64-bit)'
            ]
            for i, n in enumerate(os_list, start=1):
                print(f"{len(os_list)-i+1}) {n}")
            index = len(os_list)-int(input())
            return os_ver[os_list[index]]

    def check_wine(self):
        if not self.os_ver in ['lin32','lin64','mac32','mac64']:
            return False
        choice = input(f"\nWould you like to build a windows version of DF using wine? (y/n)\n")
        if choice.lower().startswith('y'):
            """Check for Wine installation and provide setup instructions if not found"""
            try:
                subprocess.run(['wine', '--version'], capture_output=True, check=True)
                self.add_log("Wine detected and available")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("\nWine is not installed or not in PATH.")
                print("\nWould you like me to help install Wine? (y/n)")
                if input().lower().startswith('y'):
                    # Attempt wine installation
                    self.install_wine()
                else:
                    print("\nTo install manually:")
                    print("1. Install Homebrew if you haven't already:")
                    print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                    print("2. Install Wine:")
                    print("   brew install --cask wine-stable")
                    print("\nAfter installing Wine, please run this script again.")
                    sys.exit(1)
            # Initialize Wine prefix right after confirming Wine is available
            self.wine_prefix = self.create_wine_prefix()
            env = os.environ.copy()
            env['WINEPREFIX'] = str(self.wine_prefix)
            self.wine_env = env
            return True
        else:
            return False
        
    def install_wine(self):
        if self.os_ver in ['mac32','mac64']:
            # Check if Homebrew is installed
            try:
                subprocess.run(['brew', '--version'], capture_output=True, check=True)
                print("Homebrew is already installed, proceeding with Wine installation...")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("\nHomebrew needs to be installed first. Installing Homebrew...")
                try:
                    subprocess.run(['/bin/bash', '-c', 
                        '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)'],
                        check=True)
                    print("Homebrew installed successfully!")
                except subprocess.CalledProcessError as e:
                    print(f"\nFailed to install Homebrew: {e}")
                    print("Please try installing Homebrew manually:")
                    print("/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                    sys.exit(1)

            print("\nInstalling Wine...")
            try:
                # First attempt with --no-quarantine
                try:
                    subprocess.run(['brew', 'install', '--cask', '--no-quarantine', 'wine-stable'], check=True)
                except subprocess.CalledProcessError:
                    # If --no-quarantine fails, try without it
                    subprocess.run(['brew', 'install', '--cask', 'wine-stable'], check=True)
                print("Wine installed successfully!")
                # Verify wine installation
                subprocess.run(['wine', '--version'], capture_output=True, check=True)
                self.add_log("Wine installed and verified")
                return
            except subprocess.CalledProcessError as e:
                print(f"\nFailed to install Wine: {e}")
                print("Please try installing Wine manually:")
                print("brew install --cask wine-stable")
                sys.exit(1)
        elif self.os_ver in ['lin32','lin64']:
            # For Linux, try to detect the package manager and install Wine
            try:
                # Try apt (Debian/Ubuntu)
                subprocess.run(['apt-get', '--version'], capture_output=True, check=True)
                print("\nDetected apt package manager. Installing Wine...")
                try:
                    subprocess.run(['sudo', 'apt-get', 'update'], check=True)
                    subprocess.run(['sudo', 'apt-get', 'install', '-y', 'wine'], check=True)
                    print("Wine installed successfully!")
                    self.add_log("Wine installed via apt")
                    return
                except subprocess.CalledProcessError as e:
                    print(f"\nFailed to install Wine via apt: {e}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    # Try dnf (Fedora)
                    subprocess.run(['dnf', '--version'], capture_output=True, check=True)
                    print("\nDetected dnf package manager. Installing Wine...")
                    try:
                        subprocess.run(['sudo', 'dnf', 'install', '-y', 'wine'], check=True)
                        print("Wine installed successfully!")
                        self.add_log("Wine installed via dnf")
                        return
                    except subprocess.CalledProcessError as e:
                        print(f"\nFailed to install Wine via dnf: {e}")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        # Try pacman (Arch)
                        subprocess.run(['pacman', '--version'], capture_output=True, check=True)
                        print("\nDetected pacman package manager. Installing Wine...")
                        try:
                            subprocess.run(['sudo', 'pacman', '-S', '--noconfirm', 'wine'], check=True)
                            print("Wine installed successfully!")
                            self.add_log("Wine installed via pacman")
                            return
                        except subprocess.CalledProcessError as e:
                            print(f"\nFailed to install Wine via pacman: {e}")
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        print("\nCould not detect a supported package manager.")
            
            print("\nFailed to install Wine automatically. Please install Wine manually:")
            print("For Debian/Ubuntu:\tsudo apt-get install wine")
            print("For Fedora:\t\t\tsudo dnf install wine")
            print("For Arch Linux:\t\tsudo pacman -S wine")
            sys.exit(1)

    def init_wine_dir(self, wine_prefix):
        """Initialize the Wine prefix with proper environment variables"""
        env = os.environ.copy()
        env['WINEPREFIX'] = str(wine_prefix)
        
        # Initialize the prefix with a basic wine command
        success, output = self._call_wine(['wineboot', '--init'], env=env)
        if success:
            self.add_log(f"Initialized Wine prefix directory at {wine_prefix}")
            
            # Install core Windows DLLs
            try:
                # Try to install core Windows DLLs using winetricks
                subprocess.run(['winetricks', 'corefonts', 'vcrun2005', 'vcrun2008', 'vcrun2010', 'vcrun2013', 'vcrun2015', 'vcrun2017', 'vcrun2019', 'vcrun2022'], 
                             env=env, check=True)
                self.add_log("Installed core Windows DLLs")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("\nWarning: Could not install core Windows DLLs. The game may not run properly.")
                print("Consider installing winetricks and running:")
                print("winetricks corefonts vcrun2005 vcrun2008 vcrun2010 vcrun2013 vcrun2015 vcrun2017 vcrun2019 vcrun2022")
        else:
            raise Exception(f"Failed to initialize Wine prefix: {output}")

    def check_continue_on_wine_dir_failure(self, wine_prefix, exception_message='!No exception passed', dir_fail=False, init_fail=False):
        if dir_fail:
            print(f"\nWarning: Failed to create Wine prefix directory: {exception_message}")
        if init_fail:
            print(f"\nWarning: Failed to initialize the Wine prefix: {exception_message}")
        choice_list = [
            "Input a new Wine prefix directory to try.",
            "Exit the script entirely, deal with wine on your own.",
            "Continue with the script, assuming the given Wine prefix."
        ]
        print("\nSelect how to proceed from the following list, by inputting the corresponding number:")
        for i, n in enumerate(choice_list, start=1):
            print(f"{len(choice_list)-i+1}) {n}")
        while True:
            try:
                choice_index = int(input()) - 1
                if choice_index < len(choice_list):
                    break
                else:
                    print(f"Not a valid selection, type an integer from among the choices and press enter.")
            except ValueError:
                print("Not a valid number/selection, type an integer and press enter.")
        if choice_index == 0:
            return self.create_wine_prefix(first_pass=False, fail_already=True)
        elif choice_index == 1:
            sys.exit(1)
        elif choice_index == 2:
            print(f"The launcher will still be created with prefix {wine_prefix}, but you will need to run wineboot separately.")
            return wine_prefix

    def create_wine_prefix(self, first_pass=True, fail_already=False):
        if first_pass:
            default_prefix = os.path.expanduser("~/.wine")
            print(f"\nDefault Wine prefix location is: {default_prefix}\n"+\
                f"This is best if you don't expect to customize wine for multiple uses.")
            choice = input("Would you like to use this prefix? (vs a different Wine prefix location) (y/n)\n")
            if choice.lower().startswith('y'):
                # Initialize the prefix if it doesn't exist
                if not os.path.exists(default_prefix):
                    create_choice = input("Default directory does not exist. Create it and initialize it with 'wine wineboot --init'? (y/n)\n")
                    if create_choice.lower().startswith('y'):
                        print("\nCreating Wine prefix directory...")
                        try:
                            os.makedirs(default_prefix, exist_ok=True)
                        except Exception as e:
                            return self.check_continue_on_wine_dir_failure(default_prefix, e, dir_fail=True)
                        try:
                            self.init_wine_dir(default_prefix)
                        except Exception as e:
                            return self.check_continue_on_wine_dir_failure(default_prefix, e, init_fail=True)
                        return default_prefix
                    else:
                        print("Then, please enter an existing directory.")
                        return self.create_wine_prefix(first_pass=False, fail_already=False)
                else:
                    # Check if it's already a wine prefix
                    if not os.path.exists(os.path.join(default_prefix, "system.reg")):
                        init_choice = input("This directory exists but doesn't appear to be a Wine prefix. Initialize it? (y/n)\n")
                        if init_choice.lower().startswith('y'):
                            try:
                                self.init_wine_dir(default_prefix)
                            except Exception as e:
                                return self.check_continue_on_wine_dir_failure(default_prefix, e, init_fail=True)
                        else:
                            return self.check_continue_on_wine_dir_failure(default_prefix, "User declined to initialize directory.", init_fail=True)
                    return default_prefix
        if fail_already:
            print(f"Default Wine prefix location is: {default_prefix}")
        custom_prefix = input("Enter the full path for your preferred Wine prefix:\n").strip()
        if os.path.exists(custom_prefix):
            if os.path.isdir(custom_prefix):
                # Check if it's already a wine prefix
                if not os.path.exists(os.path.join(custom_prefix, "system.reg")):
                    init_choice = input("This directory exists but doesn't appear to be a Wine prefix. Initialize it? (y/n)\n")
                    if init_choice.lower().startswith('y'):
                        try:
                            self.init_wine_dir(custom_prefix)
                        except Exception as e:
                            return self.check_continue_on_wine_dir_failure(custom_prefix, e, init_fail=True)
                    else:
                        return self.check_continue_on_wine_dir_failure(default_prefix, "User declined to initialize directory.", init_fail=True)
                return custom_prefix
            else:
                print("Error: Path exists but is not a directory.")
                return self.check_continue_on_wine_dir_failure(custom_prefix)
        else:
            create_choice = input("Directory does not exist. Create it and initialize it as a Wine prefix? (y/n)\n")
            if create_choice.lower().startswith('y'):
                try:
                    os.makedirs(custom_prefix, exist_ok=True)
                    try:
                        self.init_wine_dir(custom_prefix)
                    except Exception as e:
                        return self.check_continue_on_wine_dir_failure(custom_prefix, e, init_fail=True)
                    return custom_prefix
                except Exception as e:
                    return self.check_continue_on_wine_dir_failure(custom_prefix, e, dir_fail=True)
            else:
                print("Then, please enter an existing directory.")
                return self.create_wine_prefix(first_pass=False, fail_already=False)

    def check_target_dir(self):
        """Determine and validate the target directory for Dwarf Fortress installation.
        
        For Wine installations:
        - Defaults to Program Files/Dwarf Fortress in the Wine prefix
        - Validates that custom locations are within the Wine prefix's drive_c directory
        
        For native installations:
        - Defaults to a directory named df-{os_ver}-{date}
        - Validates write access and handles existing directories
        
        Returns:
            The validated target directory path
        """
        # If using Wine, set default target to Program Files in the prefix
        if self.use_wine:
            default_target = Path(self.wine_prefix) / "drive_c" / "Program Files" / "Dwarf Fortress"
            print(f"\nSince you're using Wine, the default target location is: {default_target}")
            print("This is recommended as it keeps the game within the Wine environment.")
            choice = input("Would you like to use this location? (y/n)\n")
            if choice.lower().startswith('y'):
                self.target_dir = default_target
            else:
                while True:
                    custom_dir = Path(input("\nIf you wish to specify a directory for the installation, "+\
                                            "it must still be within the Wine prefix's drive_c directory: "+\
                                            f'{Path(self.wine_prefix) / "drive_c"}\n'+\
                                            "Enter the full path for your preferred location, or q to quit:\n").strip())
                    if str(custom_dir).lower() == "q":
                        print("Quitting.")
                        exit(0)
                    if self._is_valid_wine_target(custom_dir):
                        self.target_dir = custom_dir
                        break
        else:
            # Set default target for non-Wine installations
            default_target = Path(f"df-{self.os_ver}-{time.strftime('%Y-%m-%d')}") # Consider -{os.environ['USER']}-
            print(f"\nThe finished DF directory will be moved to {default_target}")
            choice = input(f"Use this directory name? (y/n)\n")
            if choice.lower().startswith('y'):
                self.target_dir = default_target
            else:
                while True:
                    custom_dir = Path(input("Enter the full path for your preferred location, or q to quit:\n").strip())
                    if str(custom_dir).lower() == "q":
                        print("Quitting.")
                        exit(0)
                    if self._is_valid_target(custom_dir):
                        self.target_dir = custom_dir
                        break
        print(f"\nThe finished DF directory will be moved to:\n\t{self.target_dir}")
        return self.target_dir

    def _is_valid_target(self, target_dir):
        """Validate a target directory for basic requirements.
        
        Checks:
        - Write access to the directory
        - Handles existing directories (prompts for removal)
        
        Args:
            target_dir (Path): The directory path to validate
            
        Returns:
            bool: True if the directory is valid and ready for use, False otherwise
        """
        # Verify write access
        try:
            os.access(target_dir, os.W_OK)
        except Exception as e:
            print(e)
            print(f"\nThe target folder '{target_dir}' is not valid.")
            return False
        # Handle an existing directory
        if target_dir.exists():
            choice = input(f"\nThe target folder '{target_dir}' already exists. Do you want to remove it? (y/n)\n")
            if choice.lower().startswith('y'):
                for file_path in target_dir.glob("*"):
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        shutil.rmtree(file_path)
                shutil.rmtree(target_dir)
            else:
                return False
        return True

    def _is_valid_wine_target(self, target_dir):
        """Validate a target directory for Wine installation requirements.
        
        Checks:
        - Directory is within the Wine prefix's drive_c directory
        - Basic validation (write access, existing directory handling)
        
        Args:
            target_dir (Path): The directory path to validate
            
        Returns:
            bool: True if the directory is valid for Wine installation, False otherwise
        """
        try:
            # Convert to absolute paths for comparison
            target_abs = target_dir.resolve()
            prefix_abs = Path(self.wine_prefix).resolve()
            drive_c = prefix_abs / "drive_c"
            if drive_c in target_abs.parents:
                # Check if the target is within the Wine prefix's drive_c
                return self._is_valid_target(target_dir)
            else:
                print("\nThe target directory must be within the Wine prefix's drive_c directory.")
                print(f"Your Wine prefix is: {self.wine_prefix}")
                print("Example valid locations:")
                print(f"- {self.wine_prefix}/drive_c/Program Files/Dwarf Fortress")
                print(f"- {self.wine_prefix}/drive_c/Games/Dwarf Fortress")
                return False
        except Exception:
            return False

    def show_progress(self, package_name):
        """Display progress information for package operations"""
        self.current_package += 1
        print(f"\n[{self.current_package}/{self.packages_total}] Processing {package_name}...")

    def add_log(self, message):
        """Add a timestamped message to the log"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        self.log += f"[{timestamp}] {message}\n"
        
    def try_package(self,package_class,required=False):
        try:
            package = package_class(self.release_dir, self.cache_dir, self.os_ver, self.use_wine,required)
            self.show_progress(package.package_name)
            
            # Check dependencies
            if not package.check_dependencies(self.installed_packages):
                if not input("Continue anyway? (y/n): ").lower().startswith('y'):
                    if not required:
                        print(f"Skipping {package.package_name}")
                        self.add_log(f"Skipped {package.package_name} due to dependency issues")
                        return None
                    else:
                        raise ValueError(f"Dependency(ies) of the required package {package.package_name} are not installed")
            
            if package.run(self.installed_packages):
                self.add_log(f"Successfully unpacked {package.package_name}")
            else:
                self.add_log(f"Skipped {package.package_name}")
                return None
        except Exception as e:
            error_msg = f"Failed to download or unpack {package.package_name}: {str(e)}"
            self.add_log(error_msg)
            print(f"\nError: {error_msg}")
            if not required and not input("Continue anyway? (y/n): ").lower().startswith('y'):
                print(f"Skipping {package.package_name}")
                self.add_log(f"Skipped {package.package_name} due to dependency issues")
                return None
            raise
        return package

    def run_packages(self):
        self.current_package = 0
        self.packages_total = "?"
        self.installed_packages = {}
        
        # Ask user which source to use for Dwarf Fortress
        print("\nSelect a web source for Dwarf Fortress:")
        print("1) Bay12 Games (Official site, and hosts the free versions and classics archives)")
        print("2) itch.io (Provides DF Premium with graphics, if you have purchased it)")
        while True:
            try:
                source = int(input("Please enter either 1 or 2: "))
                if source in [1, 2]:
                    break
            except ValueError:
                continue

        # Get Dwarf Fortress version from selected source
        df_pack = self.try_package(DFBay12 if source == 1 else DFItch, required=True)
        self.df_version = df_pack.version
        self.installed_packages[df_pack.package_name] = self.df_version
        
        # Base packages that are always available
        base_packages = [
            PyLNPPackage,
            PEStarterPackPackage,
            DFHackPackage,
            TWBTPackage
        ]
        
        # OS-specific packages
        os_packages = []
        if self.os_ver in ['mac32', 'mac64']:
            if not self.use_wine:
                os_packages.append(LMPPackage)
                if self.os_ver == 'mac64':
                    os_packages.append(RubyPackage)
        elif self.os_ver in ['win32', 'win64']:
            # Windows-specific packages if any
            pass
        elif self.os_ver in ['lin32', 'lin64']:
            # Linux-specific packages if any
            pass
            
        # Combine all packages
        packages = base_packages + os_packages
        self.packages_total = len(packages)
        
        # Process each package
        for package_class in packages:
            package = self.try_package(package_class)
            if package is not None:
                self.installed_packages[package.package_name] = package.version

    def more_tilesets(self):
        """Copy additional tilesets if LNP is installed and tilesets directory exists"""
        if "LNP" in self.installed_packages and self.tileset_dir.exists():
            for tileset in self.tileset_dir.glob("*"):
                shutil.copy(tileset, f"{self.release_dir}/LNP/tilesets")

    def setup_config(self):
        # Use dfhack.init-example as dfhack.init if it exists
        dfhack_init = self.release_dir / "df" / "dfhack.init-example"
        if dfhack_init.exists():
            shutil.copy(dfhack_init, self.release_dir / "df" / "dfhack.init")
        # Modify init.txt to use TWBT if 
        # Only modify init.txt if TWBT is installed
        if 'TWBT' in self.installed_packages:
            init_txt = self.release_dir / "df" / "data" / "init" / "init.txt"
            if init_txt.exists():
                with open(init_txt, 'r+') as f:
                    content = f.read()
                    f.seek(0)
                    f.write(content.replace("[PRINT_MODE:2D]", "[PRINT_MODE:TWBT]"))
                    f.truncate()
            else:
                print("\nWarning: init.txt not found, skipping TWBT print mode configuration")
        else:
            print("\nSkipping TWBT print mode configuration as TWBT is not installed")
            
    @staticmethod
    def run_subprocess(cmd, error_msg=None):
        """Safely run a subprocess command with error handling"""
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"\nCommand failed: {' '.join(cmd)}")
            if error_msg:
                print(error_msg)
            print(f"Error: {e.stderr}")
            return False
        except Exception as e:
            print(f"\nUnexpected error running command {' '.join(cmd)}: {str(e)}")
            return False

    def _call_wine(self, arguments, env=None):
        """Run a command with Wine if needed"""
        wine_cmd = self._get_wine_command()
        if isinstance(arguments, str):
            full_command = wine_cmd + [arguments]
        elif isinstance(arguments, list):
            full_command = wine_cmd + arguments
        else:
            raise ValueError("Invalid arguments type in _call_wine")
        try:
            if env is None:
                result = subprocess.run(full_command, check=True, capture_output=True, text=True)
            else:
                result = subprocess.run(full_command, env=env, check=True, capture_output=True, text=True)
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr
        except Exception as e:
            return False, str(e)
        
    
    def _get_wine_command(self):
        """Get the appropriate Wine command for the current OS and architecture"""
        if self.os_ver.startswith('win'):
            raise ValueError("Unexpected behavior: Windows should not use Wine")
        
        # Try wine64 first, then fall back to wine
        for cmd in ['wine64', 'wine']:
            try:
                subprocess.run([cmd, '--version'], capture_output=True, check=True)
                return [cmd]
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        raise FileNotFoundError("Neither wine64 nor wine command found. Please ensure Wine is properly installed.")
    
    def create_wine_launcher(self):
        """Create a launcher script that uses Wine to run Dwarf Fortress"""
        # Get the appropriate Wine command
        wine_cmd = ' '.join(self._get_wine_command())
        
        # Common script header
        script_header = (
            "#!/bin/bash\n"
            'cd "$(dirname "$0")"\n'
        )
        
        # Common environment variables
        common_env = (
            f'WINEPREFIX="{self.wine_prefix}" '
            f'WINE_VULKAN_DRIVER=no '  # Disable Vulkan support
            f'SDL_VIDEODRIVER=windows '  # Use Windows SDL2 backend in Wine
            f'SDL_RENDER_DRIVER=opengl '  # Use OpenGL for better compatibility
            f'WINE_NOWAIT=1 '  # Disable wait functions that might cause timing issues
            f'WINE_NOWAIT_DRIVER=1 '  # Disable wait driver
            f'WINE_DISABLE_IME=1 '  # Disable IME to prevent input issues
            f'WINE_LARGE_ADDRESS_AWARE=1 '  # Enable large address space support
            f'WINE_PREFER_SYSTEM_LIBS=1 '  # Use system libraries when possible
            f'WINE_SYNC_DRIVER=fsync '  # Use fsync for better performance
            f'WINE_SYNC_FPS=60 '  # Set sync FPS to 60
        )
        
        # Debug environment variables
        debug_env = (
            f'WINE_NOWAIT_DRIVER_DEBUG=1 '  # Enable wait driver debugging
            f'WINE_NOWAIT_DRIVER_DEBUG_LEVEL=1 '  # Set debug level
            f'WINE_SYNC_FPS_DEBUG=1 '  # Enable FPS debugging
            f'WINE_SYNC_FPS_DEBUG_LEVEL=1 '  # Set FPS debug level
            f'WINE_SYNC_FPS_DEBUG_INTERVAL=1000 '  # Set FPS debug interval
            f'WINE_SYNC_FPS_DEBUG_OUTPUT=1 '  # Enable FPS debug output
            f'WINE_SYNC_FPS_DEBUG_OUTPUT_LEVEL=1 '  # Set FPS debug output level
            f'WINE_SYNC_FPS_DEBUG_OUTPUT_INTERVAL=1000 '  # Set FPS debug output interval
        )
        
        # Common script footer
        script_footer = f'{wine_cmd} "$(pwd)/Dwarf Fortress.exe" "$@"\n'
        
        # Create main launcher
        launcher_script = script_header + common_env + script_footer
        launcher_path = self.release_dir / "df" / "dfhack.sh"
        with open(launcher_path, 'w', newline='\n') as f:
            f.write(launcher_script)
        os.chmod(launcher_path, 0o755)
        self.add_log(f"Created Wine launcher script using prefix: {self.wine_prefix}")
        
        # Create debug launcher
        debug_launcher_script = script_header + common_env + debug_env + script_footer
        debug_launcher_path = self.release_dir / "df" / "dfhack-winedebug.sh"
        with open(debug_launcher_path, 'w', newline='\n') as f:
            f.write(debug_launcher_script)
        os.chmod(debug_launcher_path, 0o755)
        self.add_log(f"Created Wine debug launcher script using prefix: {self.wine_prefix}")

    def analyze_dll_dependencies(self, exe_path):
        """Analyze DLL dependencies of a Windows executable using Wine tools"""
        print(f"\nAnalyzing DLL dependencies for {exe_path.name}...")
        
        try:
            # Use winedump to analyze dependencies
            result = subprocess.run(['winedump', '-j', 'import', str(exe_path)], 
                                 env=self.wine_env, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Parse winedump output
                dlls = set()
                for line in result.stdout.split('\n'):
                    if 'DLL' in line and ':' in line:
                        dll = line.split(':')[1].strip().lower()
                        if dll.endswith('.dll'):
                            dlls.add(dll)
                
                if dlls:
                    print("\nRequired DLLs:")
                    for dll in sorted(dlls):
                        print(f"- {dll}")
                    
                    # Check which DLLs are missing
                    missing_dlls = set()
                    for dll in dlls:
                        dll_path = Path(self.wine_prefix) / "drive_c" / "windows" / "system32" / dll
                        if not dll_path.exists():
                            missing_dlls.add(dll)
                    
                    if missing_dlls:
                        print("\nMissing DLLs:")
                        for dll in sorted(missing_dlls):
                            print(f"- {dll}")
                        
                        # Use winetricks to suggest packages
                        print("\nChecking winetricks for package suggestions...")
                        try:
                            # Get list of all available winetricks packages
                            result = subprocess.run(['winetricks', '--list-all'], 
                                                 env=self.wine_env, capture_output=True, text=True)
                            if result.returncode == 0:
                                available_packages = set(result.stdout.split('\n'))
                                
                                # Map common DLL patterns to winetricks packages
                                dll_to_package = {
                                    'msvcp': 'vcrun',
                                    'msvcr': 'vcrun',
                                    'd3d': 'd3dx9',
                                    'xinput': 'xinput',
                                    'dwrite': 'dwrite',
                                    'msxml': 'msxml6',
                                    'vcruntime': 'vcrun'
                                }
                                
                                suggested_packages = set()
                                for dll in missing_dlls:
                                    for pattern, package in dll_to_package.items():
                                        if pattern in dll:
                                            # Try to find the specific version
                                            version = None
                                            if '140' in dll:
                                                version = '2015'
                                            elif '120' in dll:
                                                version = '2013'
                                            elif '110' in dll:
                                                version = '2012'
                                            elif '100' in dll:
                                                version = '2010'
                                            elif '90' in dll:
                                                version = '2008'
                                            elif '80' in dll:
                                                version = '2005'
                                            
                                            if version:
                                                package = f"{package}{version}"
                                            
                                            if package in available_packages:
                                                suggested_packages.add(package)
                                
                                if suggested_packages:
                                    print("\nSuggested winetricks packages:")
                                    print("winetricks " + " ".join(sorted(suggested_packages)))
                                else:
                                    print("\nNo specific winetricks packages found for missing DLLs")
                            else:
                                print("\nFailed to get list of available winetricks packages")
                        except Exception as e:
                            print(f"\nError checking winetricks packages: {str(e)}")
                else:
                    print("No DLL dependencies found in winedump output")
            else:
                print("winedump analysis failed, trying alternative method...")
                
                # Try using ldd as fallback
                result = subprocess.run(['wine', 'ldd', str(exe_path)], 
                                     env=self.wine_env, capture_output=True, text=True)
                if result.returncode == 0:
                    print("\nDLL dependencies from ldd:")
                    for line in result.stdout.split('\n'):
                        if '=>' in line and '.dll' in line.lower():
                            print(line.strip())
                else:
                    print("Both winedump and ldd analysis failed")
        
        except Exception as e:
            print(f"\nError analyzing DLL dependencies: {str(e)}")

    def setup_apps(self):
        try:
            if self.use_wine:
                # Create Wine launcher if Wine is being used
                print(f"\nCreating a Wine launcher script for use in {self.os_ver}...")
                self.create_wine_launcher()
                
                # Install Dwarf Fortress into the Wine prefix
                print(f"\nInstalling Dwarf Fortress into Wine prefix {self.wine_prefix}...")
                try:
                    # Copy DF files to the Wine prefix's Program Files
                    wine_program_files = Path(self.wine_prefix) / "drive_c" / "Program Files"
                    df_wine_dir = wine_program_files / "Dwarf Fortress"
                    df_wine_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Copy all files from the df directory to the Wine prefix
                    for item in (self.release_dir / "df").iterdir():
                        dst = df_wine_dir / item.name
                        if item.is_dir():
                            shutil.copytree(item, dst)
                        else:
                            shutil.copy2(item, dst)

                    self.add_log(f"Installed Dwarf Fortress into Wine prefix {self.wine_prefix}")
                    
                    # # Analyze DLL dependencies
                    # print("\nAnalyzing Dwarf Fortress DLL dependencies...")
                    # self.analyze_dll_dependencies(df_wine_dir / "dfhack.exe")
                    # self.analyze_dll_dependencies(df_wine_dir / "Dwarf Fortress.exe")
                    
                except Exception as e:
                    print(f"\nError installing Dwarf Fortress into Wine prefix {self.wine_prefix}: {str(e)}")
                    raise
                
                # Ask about creating a shortcut
                create_shortcut = input("\nWould you like to create a shortcut to Dwarf Fortress? (y/n)\n").lower().startswith('y')
                if create_shortcut:
                    default_desktop = Path.home() / "Desktop"
                    print(f"\nDefault shortcut location is: {default_desktop}")
                    use_custom_location = input("Would you like to use a different location? (y/n)\n").lower().startswith('y')
                    if use_custom_location:
                        while True:
                            custom_dir = Path(input("\nEnter the full path for the shortcut location:\n").strip())
                            if custom_dir.exists() and custom_dir.is_dir():
                                shortcut_dir = custom_dir
                                break
                            print(f"Invalid directory: {custom_dir}")
                    else:
                        shortcut_dir = default_desktop
                    try:
                        if self.os_ver.startswith('mac'):
                            # Create macOS .app bundle
                            app_dir = shortcut_dir / "Dwarf Fortress.app"
                            app_dir.mkdir(parents=True, exist_ok=True)
                            contents_dir = app_dir / "Contents"
                            contents_dir.mkdir(parents=True, exist_ok=True)
                            
                            # Create Info.plist
                            plist_content = (
                                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                                "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
                                "<plist version=\"1.0\">\n"
                                "<dict>\n"
                                "    <key>CFBundleExecutable</key>\n"
                                "    <string>dfhack.sh</string>\n"
                                "    <key>CFBundleIconFile</key>\n"
                                "    <string>df.icns</string>\n"
                                "    <key>CFBundleIdentifier</key>\n"
                                "    <string>com.bay12games.dwarffortress</string>\n"
                                "    <key>CFBundleName</key>\n"
                                "    <string>Dwarf Fortress</string>\n"
                                "    <key>CFBundlePackageType</key>\n"
                                "    <string>APPL</string>\n"
                                "    <key>CFBundleShortVersionString</key>\n"
                                "    <string>1.0</string>\n"
                                "</dict>\n"
                                "</plist>"
                            )
                            with open(contents_dir / "Info.plist", 'w') as f:
                                f.write(plist_content)
                            
                            # Create MacOS directory and launcher script
                            macos_dir = contents_dir / "MacOS"
                            macos_dir.mkdir(parents=True, exist_ok=True)
                            hack_script = (
                                "#!/bin/bash\n"
                                f'cd "{df_wine_dir}"\n'
                                f'WINEPREFIX="{self.wine_prefix}" {self._get_wine_command()[0]} dfhack.exe "$@"'
                            )
                            with open(macos_dir / "dfhack.sh", 'w', newline='\n') as f:
                                f.write(hack_script)
                            os.chmod(macos_dir / "dfhack.sh", 0o755)
                            
                            # Create Resources directory and copy icon if available
                            resources_dir = contents_dir / "Resources"
                            resources_dir.mkdir(parents=True, exist_ok=True)
                            icon_path = self.release_dir / "df" / "data" / "art" / "df.icns"
                            if icon_path.exists():
                                shutil.copy2(icon_path, resources_dir)
                        
                        elif self.os_ver.startswith('lin'):
                            # Create Linux .desktop file
                            desktop_entry = (
                                "[Desktop Entry]\n"
                                "Version=1.0\n"
                                "Type=Application\n"
                                "Name=Dwarf Fortress\n"
                                "Comment=Dwarf Fortress with DFHack\n"
                                f'Exec=cd "{df_wine_dir}" && WINEPREFIX="{self.wine_prefix}" {self._get_wine_command()[0]} dfhack.exe %F\n'
                                f'Path={df_wine_dir}\n'
                            )
                            # Add icon if it exists
                            icon_path = Path(f"{df_wine_dir}/data/art/df.png")
                            if icon_path.exists():
                                desktop_entry += f'Icon={df_wine_dir}/data/art/df.png\n'
                            desktop_entry += (
                                "Terminal=false\n"
                                "Categories=Game;StrategyGame;\n"
                            )
                            with open(shortcut_dir / "dwarffortress.desktop", 'w', newline='\n') as f:
                                f.write(desktop_entry)
                            os.chmod(shortcut_dir / "dwarffortress.desktop", 0o755)
                        self.add_log(f"Created shortcut for Dwarf Fortress running with DFHack on Wine.")
                    except Exception as e:
                        print(f"\nError creating shortcut: {str(e)}")
                        raise
            elif self.os_ver in ['mac32','mac64']:
                # macOS native setup
                apps_dir = Path("apps")
                if not apps_dir.exists():
                    raise FileNotFoundError("Required 'apps' directory not found")
                
                # Copy base app and remove_quarantine script
                shutil.copytree(apps_dir / "Dwarf Fortress.app", self.release_dir / "Dwarf Fortress.app")
                shutil.copy(apps_dir / "remove_quarantine", self.release_dir / "remove_quarantine")
                
                # Set up PyLNP if installed
                if 'PyLNP' in self.installed_packages:
                    shutil.copy(apps_dir / "Dwarf Fortress.app/Contents/Resources/df.icns", 
                              self.release_dir / "PyLNP.app/Contents/Resources/df.icns")
                    shutil.copy(apps_dir / "LNPInfo.plist", self.release_dir / "PyLNP.app/Contents/Info.plist")
                    os.rename(self.release_dir / "PyLNP.app", self.release_dir / "Dwarf Fortress LNP.app")
                    (self.release_dir / "Dwarf Fortress LNP.app").touch()
            elif self.os_ver in ['win32','win64']:
                # Windows native setup
                if 'DFHack' in self.installed_packages:
                    # Create a batch file launcher
                    launcher_script = (
                        "@echo off\n"
                        "cd /d \"%~dp0\"\n"
                        "start dfhack.exe %*\n"
                    )
                    launcher_path = self.release_dir / "df" / "dfhack.bat"
                    with open(launcher_path, 'w', newline='\r\n') as f:
                        f.write(launcher_script)
                    self.add_log("Created Windows launcher script")
            elif self.os_ver in ['lin32','lin64']:
                # Linux native setup
                if 'DFHack' in self.installed_packages:
                    # Create a shell script launcher
                    launcher_script = (
                        "#!/bin/bash\n"
                        'cd "$(dirname "$0")"\n'
                        './dfhack "$@"\n'
                    )
                    launcher_path = self.release_dir / "df" / "dfhack.sh"
                    with open(launcher_path, 'w', newline='\n') as f:
                        f.write(launcher_script)
                    os.chmod(launcher_path, 0o755)
                    self.add_log("Created Linux launcher script")
        except FileNotFoundError as e:
            print(f"\nError setting up apps: Required file not found - {e.filename}")
            raise
        except Exception as e:
            print(f"\nError setting up apps: {str(e)}")
            raise

    def move_target(self):
        shutil.move(self.release_dir, self.target_dir)
        with open(self.target_dir / "dfdl_build.txt", 'w') as log_file:
            log_file.write(self.log)

    def run(self):
        self.run_packages()
        self.more_tilesets()
        self.setup_config()
        self.setup_apps()
        self.move_target()

if __name__ == "__main__":
    Release().run()
