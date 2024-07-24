# Gaia2BSC5.py
- RMS uses the Gaia star catalogue which only used faint stars. When using Skyfit2 it might be easer to use the BSC5 catalogue, which includes familiar constelations. This script looks recursively for any instance of the file named .config and changes the line 'star_catalog_file: gaia_dr2_mag_11.5.npy' to 'star_catalog_file: BSC5'. This is especially useful if there are many .config files to edit.
It has a single argument and that is the path to the folder where you want the script to start looking.
- WARNING: Just make sure that none of these edited .config files gets back to the system running RMS.
# Makekml.py
- After running "wmpl\Formats\ECSV.py" or "wmpl\Trajectory\Correl ateRMS.py" a file is generated with a name ending in report.txt. Use the full path of this file as an arguement and it will generate a KML in the same folder as report.txt with a track of the meteor in 3D.
- You need to install the simplekml library before using this "pip install simplekml
- I need to find a better way to get the details from report.txt as the format of this file has changed a couple of times since I wrote it.
# extract_bz2.py
- When you get a whole lot of bz2 files to extract, this can do it all in one go. Use the path to the folder where the files are as an arguement
# extract_captured_stack.py
- Extracts only files ending in the name captured_stack.jpg from a list of .bz2 files. Use the path to the folder where the files are as an arguement
