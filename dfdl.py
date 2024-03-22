#!/usr/bin/env python3

import os
import json
import platform
import shutil
import sys
import tempfile
import subprocess
import time
import urllib.request
# import zipfile
# import tarfile
from pathlib import Path
from html.parser import HTMLParser

class PackageHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr in attrs:
                if attr[0] == "href":
                    self.hrefs.append(attr[1])

class Package:
    def __init__(self, release_dir, cache_dir, os_ver):
        self.release_dir = release_dir
        self.cache_dir = cache_dir
        self.os_ver = os_ver
        
    def match_name(self, name):
        return self.filter_name(name)
    
    def choose(self):
        list = self.get_list()
        if list == []:
            raise ValueError("Failed to retrieve any matching versions")
        else:
            print("\nSelect a version from the following list, by inputting the corresponding number:")
            for i, n in enumerate(reversed(list), start=1):
                print(f"{len(list)-i+1}) {n['name']}")
            while True:
                try:
                    index = int(input()) - 1
                    break
                except ValueError:
                    print("Not a valid number/selection, type an integer and press enter.")
            choice = list[index]
            self.filename, self.url = choice['name'], choice['url']

    def download(self):
        # subprocess.run(["curl", "-L", "-C", "-", self.url, "-o", f"{self.cache_dir}/{self.filename}"])
        # urllib.request.urlretrieve(self.url, f"{self.cache_dir}/{self.filename}")
        if not os.path.isfile(f"{self.cache_dir}/{self.filename}"):
            with urllib.request.urlopen(self.url) as response, open(f"{self.cache_dir}/{self.filename}", 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

    def extract(self):
        self.unpack(f"{self.cache_dir}/{self.filename}", self.release_dir)

    def run(self):
        self.choose()
        self.download()
        self.extract()

    def filter_name(self, name): 
        # os_rem = {
        #     # {'ver': '', 'rem': ['mac','osx','OSX','lin','Lin','win','Win','64','32']},
        #     'Windows (32-bit)': ['mac','osx','OSX','lin','Lin','64'],
        #     'Windows (64-bit)': ['mac','osx','OSX','lin','Lin','32'],
        #     'Linux (32-bit)': ['mac','osx','OSX','win','Win','64'],
        #     'Linux (64-bit)': ['mac','osx','OSX','win','Win','32'],
        #     'Mac (32-bit)': ['lin','Lin','win','Win','64'],
        #     'Mac (64-bit)': ['lin','Lin','win','Win','32']
        # }
        os_rem = {
            # {'ver': '', 'rem': ['mac','osx','OSX','lin','Lin','win','Win','64','32']},
            'win32': ['mac','osx','OSX','lin','Lin','64'],
            'win64': ['mac','osx','OSX','lin','Lin','32'],
            'lin32': ['mac','osx','OSX','win','Win','64'],
            'lin64': ['mac','osx','OSX','win','Win','32'],
            'mac32': ['lin','Lin','win','Win','64'],
            'mac64': ['lin','Lin','win','Win','32']
        }
        wrong_match = False
        for rem in os_rem[self.os_ver]:
            wrong_match = wrong_match or rem in name
        return not wrong_match

    def unpack(self, src, dest):
        shutil.unpack_archive(src, dest)

    def unzip(self, src, dest):
        shutil.unpack_archive(src, dest, "zip")
    #     with zipfile.ZipFile(src, 'r') as zip_ref:
    #         zip_ref.extractall(dest)

    def untarbz2(self, src, dest):
        shutil.unpack_archive(src, dest, "bztar")
    #     with tarfile.open(src, 'r:bz2') as tar_ref:
    #         tar_ref.extractall(dest)

class BitBucketPackage(Package):
    def get_list(self):
        if not hasattr(self, '_list'):
            with urllib.request.urlopen(self.releases_url) as response:
                data = json.load(response)
            self._list = [
                {'name': a['name'], 'url': a['links']['self']['href']}
                for a in data['values'] if self.match_name(a['name'])
            ]
        return self._list

class GitHubPackage(Package):
    def get_list(self):
        # print("Retrieving version list from GitHub API")
        if not hasattr(self, '_list'):
            page = 1
            assets = []
            while True:
                # Construct the URL with pagination parameters
                page_url = f"{self.releases_url}?page={page}&per_page=100"  # Adjust per_page as needed

                response = urllib.request.urlopen(page_url)
                if response.status == 200:
                    data = json.loads(response.read())
                    current_assets = [a for r in data for a in r.get('assets', []) if self.match_name(a.get('name', ''))]
                    assets.extend(current_assets)
                    
                    # Check if there are more pages to fetch
                    if len(current_assets) < 100:  # Assuming 100 releases per page, adjust if needed
                        break
                    else:
                        page += 1
                else:
                    if len(assets) == 0:
                        print("Failed to fetch data from GitHub API")
                        return []
                
            self._list = [{'name': a.get('name', ''), 'url': a.get('browser_download_url', '')} for a in assets]
        return self._list

class PyLNPPackage(GitHubPackage):
    # def match_name(self, name):
    #     if self.os_ver == 'mac32':
    #         return ('OSX' in name or 'macOS' in name) and '64' not in name
    #     if self.os_ver == 'mac64':
    #         return ('OSX' in name or 'macOS' in name) and '32' not in name

    @property
    def releases_url(self):
        return "https://api.github.com/repos/Pidgeot/python-lnp/releases"

    def extract(self):
        if self.os_ver == 'mac32' or self.os_ver == 'mac64':
            subprocess.run(["ditto", "-xk", f"{self.cache_dir}/{self.filename}", self.release_dir])
        else:
            self.unzip(f"{self.cache_dir}/{self.filename}", self.release_dir)

class DFPackage(Package):    
    def match_name(self, name):
        os_in = {
            'win32': 'zip',
            'win64': 'zip',
            'lin32': 'linux',
            'lin64': 'linux',
            'mac32': 'osx',
            'mac64': 'osx'
        }
        return self.filter_name(name) and os_in[self.os_ver] in name
    
    def get_list(self):
        if not hasattr(self, '_list'):
            with urllib.request.urlopen("http://bay12games.com/dwarves/older_versions.html") as response:
                parser = PackageHTMLParser()
                parser.feed(response.read().decode())
            self._list = [{'name': href, 'url': f"http://bay12games.com/dwarves/{href}"} for href in parser.hrefs if self.match_name(href)]
        return self._list

    # def extract(self):
    #     self.untarbz2(f"{self.cache_dir}/{self.filename}", self.release_dir)

class DFHackPackage(GitHubPackage):
    def match_name(self, name):
        os_in = {
            'win32': 'Windows',
            'win64': 'Windows',
            'lin32': 'Linux',
            'lin64': 'Linux',
            'mac32': 'OSX',
            'mac64': 'OSX'
        }
        return self.filter_name(name) and os_in[self.os_ver] in name

    @property
    def releases_url(self):
        return "https://api.github.com/repos/DFHack/dfhack/releases"

    def extract(self):
        self.untarbz2(f"{self.cache_dir}/{self.filename}", f"{self.release_dir}/df_osx")

class TWBTPackage(GitHubPackage):
    # def match_name(self, name):
    #     return 'osx' in name

    @property
    def releases_url(self):
        return "https://api.github.com/repos/thurin/df-twbt/releases"

    def extract(self):
        self.unzip(f"{self.cache_dir}/{self.filename}", f"{self.release_dir}/twbt")
        for ext in ['png', 'lua', 'dylib']:
            for file_path in Path(f"{self.release_dir}/twbt").glob(f"*.{ext}"):
                if ext == 'dylib':
                    shutil.move(file_path, f"{self.release_dir}/df_osx/hack/plugins")
                elif ext == 'lua':
                    shutil.move(file_path, f"{self.release_dir}/df_osx/hack/lua")
                elif ext == 'png':
                    # print(f"{self.release_dir}/df_osx/data/art/{file_path.name}")
                    # print(os.path.isfile(f"{self.release_dir}/df_osx/data/art/{file_path.name}"))
                    if os.path.isfile(f"{self.release_dir}/df_osx/data/art/{file_path.name}"):
                        os.remove(f"{self.release_dir}/df_osx/data/art/{file_path.name}")
                    shutil.move(file_path, f"{self.release_dir}/df_osx/data/art")
        if os.path.isfile(f"{self.release_dir}/df_osx/data/init/overrides.txt"):
            os.remove(f"{self.release_dir}/df_osx/data/init/overrides.txt")
        shutil.rmtree(f"{self.release_dir}/twbt")

class PEStarterPackPackage(Package):    
    def get_list(self):
        if not hasattr(self, '_list'):
            with urllib.request.urlopen("http://df.wicked-code.com") as response:
                parser = PackageHTMLParser()
                parser.feed(response.read().decode())
            self._list = [{'name': href, 'url': f"http://df.wicked-code.com/{href}"} for href in reversed(parser.hrefs) if 'zip' in href]
        return self._list
    

    def extract(self):
        self.unzip(f"{self.cache_dir}/{self.filename}", self.release_dir)
        for file_path in Path(self.release_dir).glob("*.exe"):
            os.remove(file_path)
        for file_path in Path(self.release_dir).glob("Dwarf Fortress *"):
            shutil.rmtree(file_path)
        for file_path in Path(self.release_dir, "LNP", "utilities").glob("*"):
            if file_path.is_file():
                os.remove(file_path)
            elif file_path.is_dir():
                shutil.rmtree(file_path)


class Release:
    def __init__(self):
        self.os_ver = self.check_os()
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.release_dir = self.temp_dir_obj.name
        print(f"Preparing temporary directory at {self.release_dir}")
        self.cache_dir = Path("package_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # self.target_dir = f"df-{os.environ['USER']}-{int(time.time())}"
        self.target_dir = f"df-{os.environ['USER']}-{time.strftime('%Y-%m-%d')}"
        print(f"Will move finished directory to target folder {self.target_dir}")

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
        choice = input(f"\nSystem detected as '{detected_os}'. Is this correct? (y/n)")
        if choice.lower() == "y":
            return os_ver[detected_os]
        else:
            print("\nSelect your OS, by inputting the corresponding number:")
            # os_list = [
            #     {'desc': 'Windows (32-bit)', 'ver': 'win32'},
            #     {'desc': 'Windows (64-bit)', 'ver': 'win64'},
            #     {'desc': 'Linux (32-bit)', 'ver': 'lin32'},
            #     {'desc': 'Linux (64-bit)', 'ver': 'lin64'},
            #     {'desc': 'Mac (32-bit)', 'ver': 'mac32'},
            #     {'desc': 'Mac (64-bit)', 'ver': 'mac64'}
            # ]
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
            # choice = os_list[index]
            return os_ver[os_list[index]]

    def verify_target(self):
        if os.path.exists(self.target_dir):
            choice = input(f"\nThe target folder '{self.target_dir}' already exists. Do you want to overwrite it? (y/n)")
            if choice.lower() == "y":
                # shutil.rmtree(self.target_dir,ignore_errors=True)
                for file_path in Path(self.target_dir).glob("*"):
                    if file_path.is_file():
                        os.remove(file_path)
                    elif file_path.is_dir():
                        shutil.rmtree(file_path)
                shutil.rmtree(self.target_dir)
            else:
                print("Quitting.")
                exit(0)

    def run_packages(self):
        PyLNPPackage(self.release_dir, self.cache_dir, self.os_ver).run()
        PEStarterPackPackage(self.release_dir, self.cache_dir, self.os_ver).run()
        DFPackage(self.release_dir, self.cache_dir, self.os_ver).run()
        DFHackPackage(self.release_dir, self.cache_dir, self.os_ver).run()
        TWBTPackage(self.release_dir, self.cache_dir, self.os_ver).run()

    def copy_additional_tilesets(self):
        for tileset in Path("tilesets").glob("*"):
            shutil.copy(tileset, f"{self.release_dir}/LNP/tilesets")

    def setup_config(self):
        if os.path.isfile(f"{self.release_dir}/df_osx/dfhack.init-example"):
            shutil.copy(f"{self.release_dir}/df_osx/dfhack.init-example", f"{self.release_dir}/df_osx/dfhack.init")
        with open(f"{self.release_dir}/df_osx/data/init/init.txt", 'r+') as f:
            content = f.read()
            f.seek(0)
            f.write(content.replace("[PRINT_MODE:2D]", "[PRINT_MODE:TWBT]"))
            f.truncate()

    def setup_apps(self):
        shutil.copytree("apps/Dwarf Fortress.app", f"{self.release_dir}/Dwarf Fortress.app")
        shutil.copy("apps/Dwarf Fortress.app/Contents/Resources/df.icns", f"{self.release_dir}/PyLNP.app/Contents/Resources/df.icns")
        shutil.copy("apps/LNPInfo.plist", f"{self.release_dir}/PyLNP.app/Contents/Info.plist")
        shutil.copy("apps/remove_quarantine", f"{self.release_dir}/remove_quarantine")
        os.rename(f"{self.release_dir}/PyLNP.app", f"{self.release_dir}/Dwarf Fortress LNP.app")
        Path(f"{self.release_dir}/Dwarf Fortress LNP.app").touch()

    def move_target(self):
        shutil.move(self.release_dir, self.target_dir)

    def run(self):
        self.verify_target()
        self.run_packages()
        self.copy_additional_tilesets()
        self.setup_config()
        self.setup_apps()
        self.move_target()

if __name__ == "__main__":
    Release().run()
