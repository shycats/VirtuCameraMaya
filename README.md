# VirtuCameraMaya
Python Maya plug-in to make camera motion capture with VirtuCamera iOS App

How to install VirtuCameraMaya:

VirtuCameraMaya is provided as a Python Maya® Plug-in. The installation is pretty straight forward: 

1. Unzip the archive, you can download it from the releases page.

2. Copy the contents of the archive: a folder named virtuCameraMaya and a file named virtuCameraMayaPlugin.py

3. Paste them in one of the following directories, depending on your operating system. If the plug-ins folder doesn’t exist, create it:

Windows: \Users\<username>\Documents\maya\<version>\plug-ins\
MacOS: /Users/<username>/Library/Preferences/Autodesk/maya/<version>/plug-ins/
Linux: $HOME/maya/<version>/plug-ins/

Note for MacOS users: If you can’t find the Library folder, it’s probably hidden. You can use Cmd+Shift+. to show hidden files.

4. Open Maya, go to menu Windows > Settings/Preferences > Plug-in Manager and make sure virtuCameraMayaPlugin.py is loaded.


Done! you should have a new shelf from VirtuCamera ready to be used.

If you prefer it, you can add the plug-in folder path to the MAYA_PLUG_IN_PATH environment variable.
