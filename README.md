# Gaia2BSC5.py

- RMS uses the Gaia star catalogue which only used faint stars. When using Skyfit2 it might be easer to use the BSC5 catalogue, which includes familiar constelations. This script looks recursively for any instance of the file named .config and changes the line 'star_catalog_file: gaia_dr2_mag_11.5.npy' to 'star_catalog_file: BSC5'. This is especially useful if there are many .config files to edit.
  It has a single argument and that is the path to the folder where you want the script to start looking.
- WARNING: Just make sure that none of these edited .config files gets back to the system running RMS.

# Makekml.py

- After running "wmpl\Formats\ECSV.py" or "wmpl\Trajectory\CorrelateRMS.py" a file is generated with a name ending in report.txt. Use the full path of this file as an argument and it will generate a KML in the same folder as report.txt with a track of the meteor in 3D.
- You need to install the simplekml library before using this "pip install simplekml
- This version will read the coordinates correctly, despite minor differences in the format of the report file.

# extr_bz2.py

- When you get a whole lot of bz2 files to extract, this can do it all in one go. Use the path to the folder where the files are as an argument

# extr_captured_stack.py

- Extracts only files ending in the name captured_stack.jpg from a list of .bz2 files. Use the path to the folder where the files are as an argument
- This is useful for quickly assessing the bz2 files produced by the event monitor. Before starting, extract the captured_stack.jpg image to see what is there

# extr_FTPd.py

- Extracts files with the pattern _FTPdetectinfo_.* and *platepars_all*.* from bz2 files in the path
- Places the resulting files in a folder named after the first 6 characters of the archive name.
- 99% of this is written by ChatGPT
