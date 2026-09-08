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

# plot_r_gain_data.py

- This is for analysing the data produced by the lux meter on the Fireballs360 system.
- Works with files with the name R_GAIN\_???\_YYYYMMDD.csv
- At a minimum it needs as an argument the date in the file name in the format YYYYMMDD
- Other arguements are described with "python plot_r_gain_data.py -h"

# new_extractBz2.py

- A re-work of extractBz2 which allows for a second arguement being a different folder to write the files to. Plus it reduces the path down to only the folder that the files are actually in. Will skip an existing extraction, unless the --overwrite switch is used.

# add_txt.py

- Adds text to a png or jpg file. This is useful to add your station number to the image you use for wallpaper
  Usage: python add_text.py <image_path> "Your Text Here" y_fraction (Default is 0.1 which is 10% of the way down the image)

# SetiUploaderWrapper.py

- This replaces SetiUploader.py as the External Script for RMS. It runs logMeteorStats.sh and then runs SetiUploader. If SetiUploader.py isn't present it just runs logMeteorStats.sh

# NodeRedApp.json

- My Node Red App for monitoring multiple RMS cameras. Used in conjunction with https://github.com/markmac99/rms_mqtt

# label_images.py

- Takes 1 arguement which is a path and will recursively find all picture files in that path and will add the filename to the bottom LH corner of the picture. The new picture is save in the default directory.

# install_rustdesk.sh

- Installs Rustdesk. Uses two arguements, Station ID and Rustdesk Password. If install_rustdesk.ini is in the same folder, it will include Rustdesk ID server details in the installation. Tested on Buster, Bookworm and Trixie. Should also work on x86 machines.

# remove_rustdesk.sh

- Removes an installation of Rustdesk

# concat_mkv

- Concatenates a list of mkv movies. One arguement a folder containing the mkv files

# concat_mp4

- Concatenates a list of mp4 movies. One arguement a folder containing the mp4 files

# win_to_wsl.py

- Converts a Windows path to a Linux style path. Returns the path to screen and loads it into the copy buffer.

# GRMSShutdown.sh

- A graceful shutdown for a multi camera RMS system

# GRMSShutdown.wrapper.sh

- Runs GRMSShutdown.sh and then powers off the machine. For use with a UPS when battery low.

# meteor_scan.py

- Scans a folder of video files and looks for something that might be a meteor. Use with mask.bmp to avoid scanning areas that are not sky. If scanning videos from multiple cameras, rename the mask with the camera code. ie. If the video's name is NZ005C_20260819_065608_490671_video.mkv then rename mask.bmp to NZ0005C_mask.bmp and thise videos will be scanned with that mask.

# meteor_scan_simple.py

- Simplified for of meteor_scan.py that displays only the candidate files at the end

# get_emails.py

- Scans a folder of saved emails and extracts any email addresses after the 'To:' line. Writes the result to a txt file in the same folder

# archive_maxpixel_events.py

- I used this to extract and archive specific events in the CapturedFiles folder. I marked the events I wanted by viewing the FF file in CMN_binViewer and the created a jpg file of the event. Then ran this script which will find the jpg file and then extract the jpg, FF & FR files relating to the event and add them to a zip archive.