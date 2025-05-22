# dfdl.py - Dwarf Fortress Starter Pack generator for Mac, running in Python

A python-based dwarf fortress installer and lazy newb pack generator, which 
should hopefully be somewhat future-proof. I started by converting Juan 
Pumarino's ruby-based script (https://github.com/jipumarino/dfdl), and have 
reduced the dependencies to just base python 3.6+ and relevant command line 
utilities everyone should generally have already.


## Running

### Installing Dwarf Fortress
You start the install script from a terminal by navigating to the dfdl directory and 
running

```
./dfdl.py
```
or
```
python dfdl.py
```

While running, the script will provide a list of different versions of each 
package or utility option, and you may choose one by entering its number in 
the command line and pressing enter. 

### Starting Dwarf Fortress

After installation, here's how to start Dwarf Fortress on different platforms:

#### macOS
- **Native Version**: Double-click `Dwarf Fortress.app` in the installation directory
- **With LNP**: Double-click `Dwarf Fortress LNP.app` to use the Lazy Newb Pack interface
- **With DFHack**: Double-click `Dwarf Fortress.app` - DFHack is integrated into the native app
- **Wine Version**: Double-click the created shortcut on your Desktop (or wherever you placed it)

#### Linux
- **Native Version**: Run `./df` in the installation directory
- **With DFHack**: Run `./dfhack.sh` in the installation directory
- **Wine Version**: Double-click the created `.desktop` file or run it from your applications menu

#### Windows
- **Native Version**: Run `Dwarf Fortress.exe` in the installation directory
- **With DFHack**: Run `dfhack.bat` in the installation directory

#### Wine (on macOS/Linux)
- **With DFHack**: Double-click the created shortcut or run the launcher script
- **Manual Start**: Navigate to the installation directory and run:
  ```bash
  WINEPREFIX="~/.wine" wine dfhack.exe
  ```
  (Replace `~/.wine` with your custom Wine prefix if you used one)

## Troubleshooting

I've only testing this on my personal mac. Using this script I'm able to 
generate a native macOS directory with with both LNP and the dfhack Dwarf 
Fortress.apps using the 64 bit mac versions of all packages (with df 47.05). 
If you're on an Intel Mac and aren't sure about the options, inputting y or 
1 for every prompt except using wine should generally build a working 
install for you.

If you have issues, or are trying it out on system other than a 64-bit MacOS 
on an Intel chipset, let me know or start a discussion in this repo. It 
probably doesn't work on other OSs atm, but it will still try downloading 
all the packages. 32-bit is also no longer supported by a number of tools, 
and so will not work for newer df versions.

## Dependencies

The script should have no dependencies other than base python 3.6+. On mac 
it calls osx-specific commands like `ditto` as subprocesses, which are 
included in all MacOS distributions. Regardless, if a command-line utility 
is not present consider using homebrew or another relevant package installer.

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
