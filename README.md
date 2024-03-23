# dfdl.py - Dwarf Fortress Starter Pack generator for Mac, running in Python

A python-based lazy newb pack generator, which should hopefully be somewhat 
future-proof. I started by converting Juan Pumarino's ruby-based script 
(https://github.com/jipumarino/dfdl), and have reduced the dependencies to 
just base python 3.6+ and relevant command line utilities everyone should 
generally have already. If you have issues, or are trying it out on an OS 
other than 64-bit MacOS, let me know.


## From jipumarino's readme:

It downloads various packages and puts them together. It currently filters the
available Mac downloads for the following packages, and lets the user choose a
version for each:

- Dwarf Fortress: http://bay12games.com/dwarves/older_versions.html
- PyLNP: https://bitbucket.org/Pidgeot/python-lnp/downloads/
- PeridexisErrant's Starter Pack, for the graphics:
            http://dffd.bay12games.com/file.php?id=7622
- DFHack: https://github.com/DFHack/dfhack/releases
- TWBT: https://github.com/mifki/df-twbt/releases

It generates a 'df' folder with everything in the right place. I rename
PyLNP.app to 'Dwarf Fortress LNP.app' because that's the way it works better
with my own Mac launcher, and I additionally create an AppleScript-based app
for running dfhack directly, without the LNP, which just uses the options
that were used by the LNP the last time.

The script relies on HTML scrapping and name matching for most packages, which
could break at any moment.

I'm currently using PeridexisErrant's Starter Pack only for its collection of
graphic packs, I may change this to actually retrieve them from their source.

I am _not_ retrieving any utilities at the moment. In the future I expect to
download all utilities currently provided by PE's starter pack that have a
Mac version.

## Running

You start the script from a terminal by running

```
./dfdl.py
```

It will provide a list of different versions of each package, you choose one 
by entering its number and pressing enter. I've generated a working directory 
with both LNP and the dfhack Dwarf Fortress.apps using the latest 64 bit mac 
versions of all packages (with df 47.05), except that I used the 0.47.05-r09 
version of PE's Starter Pack, as the later versions gave archive format errors.

## Dependencies

The script should have no dependencies other than base python 3.6+. On mac 
it calls the os-specific command `ditto` as a subprocess, which should be 
included in every mac distribution. If a command line utility like `ditto` 
is not present consider using homebrew or other relevant package installers.

## Token Management

If you wish to modify this to use github tokens I recommend modifying the 
script to use a json configuration file, as so:

A 'config.json' file with:
```
{
    "github_token": "your_github_token_here"
}
```
Another class in the dfdl.py script:
```
class Config:
    @staticmethod
    def load():
        with open("config.json", 'r') as f:
            return json.load(f)

    @staticmethod
    def github_token():
        return Config.load()["github_token"]
```
Which can be stored as a property of the Release class set during init:
```
self.config = Config.load()
```
You would then need to use it in the get_list method of the GitHubPackage 
class in some way...