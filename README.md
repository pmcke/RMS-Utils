# gaia2Gmnsc.py

- Changes the line in any .config file below the path in the arguement from 'star_catalog_file: gaia_dr2_mag_11.5.npy' to 'star_catalog_file: GMN_StarCatalog'. This is now the star catalog that should be used both on the Pi and when using Skyfit2.

  It has a single argument and that is the path to the folder where you want the script to start looking.

# makeKml.py

- After running "wmpl\Formats\ECSV.py" or "wmpl\Trajectory\CorrelateRMS.py" a file is generated with a name ending in report.txt. Use the full path of this file as an argument and it will generate a KML in the same folder as report.txt with a track of the meteor in 3D.
- You need to install the simplekml library before using this "pip install simplekml
- This version will read the coordinates correctly, despite minor differences in the format of the report file.

# extactBz2.py

- When you get a whole lot of bz2 files to extract, this can do it all in one go. Use the path to the folder where the files are as an argument

# extractCapStack.py

- Extracts only files ending in the name captured_stack.jpg from a list of .bz2 files. Use the path to the folder where the files are as an argument
- This is useful for quickly assessing the bz2 files produced by the event monitor. Before starting, extract the captured_stack.jpg image to see what is there

# extractFtpd.py

- Extracts files with the pattern _FTPdetectinfo_.* and *platepars_all*.* from bz2 files in the path
- Places the resulting files in a folder named after the first 6 characters of the archive name.
- 99% of this is written by ChatGPT

# plot_r_gain_data.py

- This is for analysing the data produced by the lux meter on the Fireballs360 system.
- Works with files with the name R_GAIN\_???\_YYYYMMDD.csv
- At a minimum it needs as an argument the date in the file name in the format YYYYMMDD
- Other arguements are described with "python plot_r_gain_data.py -h"

# new_extractBz2.py

- A re-work of extractBz2 which allows for a second arguement being a different folder to write the files to. Plus it reduces the path down to only the folder that the files are actually in.

# add_txt.py

- Adds text to a png or jpg file. This is useful to add your station number to the image you use for wallpaper
  Usage: python add_text.py <image_path> "Your Text Here" y_fraction (Default is 0.1 which is 10% of the way down the image)
