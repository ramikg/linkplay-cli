# Linkplay CLI

Control audio devices supporting the Linkplay API, from the comfort of your shell.  
Supports UPnP auto-discovery, so you don't even have to know your device's IP address.

![Screenshot](resources/screenshot.png)

# Installation
```bash
pip install linkplay-cli
```

After installing, run `linkplay-cli -h` to get started.

_(Requirement: Python 3.9+)_

## FAQ

### I'm getting the error `command not found: linkplay-cli` 

The installed script is probably not in your `PATH`.  
Run `pip install` with the `-v` flag to find out the script's directory, and make sure that it's in your path.

### I'm getting the error `unknown command`

Not all commands exist in all devices.

### Some commands have no effect

This CLI utility is a wrapper around the Linkplay API, which may not work in all situations.  
For example, most media control commands won't work when the audio is playing from your browser.
