# dfdl.py - Dwarf Fortress Starter Pack generator for Mac, running in Python

A python-based lazy newb pack generator, which should hopefully be somewhat 
future-proof. I started by converting Juan Pumarino's ruby-based script 
(https://github.com/jipumarino/dfdl), and have reduced the dependencies to 
just base python 3.6+ and relevant command line utilities everyone should 
generally have already.

If you have issues, or are trying it out on an OS other than 64-bit MacOS, 
let me know. It probably won't work on other OSs atm, but it will still try 
downloading all the packages. 32-bit is also no longer supported by a number 
of tools, and so would never work for newer df versions.


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
it calls the osx-specific command `ditto` as a
subprocess, which is included in every MacOS distribution. If a command 
line utility is not present consider using homebrew or another relevant 
package installers.

## Token Management

If you wish to use github tokens, you can do so with a config.json file. 
Github no longer seems to provide a speed bost on api calls though, so as 
far as I can tell you do not need to do this. If you want to though, you 
can generate a config.json by calling the script with a --gen_config flag:

```
./dfdl.py --gen_config
```

The 'config.json' file will initially have the following format:
```
{
    "github_token": "your_github_token_here"
}
```
If you want to know more about personal access tokens, see:

https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

If you want to know more about authorization on the API generally, see:

https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api