"""
Makekml.py by Peter McKellar with input from Jesse Stayte and ChatGPT. 26 September 2023

After running the trajectory solver, one of the resulting files is a text file with name 
ending in report.txt. This script extracts the beginning lat, long & alt and the end lat, long & alt from that file 
and creates a kml file called Fireball.kml in the same folder as the *report.txt file.

It only has one argument and that is the full path and file name of the *.txt file. That can be obtained in Windows 
by right clicking on the file name and selecting Copy as Path.
"""


import simplekml
import os
import sys


file_path = sys.argv[1]
if os.path.isfile(file_path):

    try:
        with open(file_path, 'r') as f:

            # Initialize variables to store extracted values
            blat, blong, balt = None, None, None
            elat, elong, ealt = None, None, None

            for line in f:
                if line.strip() == 'Begin point on the trajectory:':
                    blat = float(next(f)[14:24])
                    _ = next(f) 
                    blong = float(next(f)[14:24])
                    _ = next(f) 
                    balt = float(next(f)[14:24])
                    # print(blat, blong, balt)
                    for item in range(3):  # Skip 3 lines
                        _ = next(f) 
                    elat = float(next(f)[14:24])
                    _ = next(f) 
                    elong = float(next(f)[14:24])
                    _ = next(f) 
                    ealt = float(next(f)[14:24])
                    break

        kml = simplekml.Kml()

        coordinates = [(blong, blat, balt), (elong, elat, ealt)]

        lin = kml.newlinestring(name="Fireball")
        lin.coords = coordinates
        lin.altitudemode = simplekml.AltitudeMode.absolute
        lin.style.linestyle.color = simplekml.Color.red  # Red
        lin.style.linestyle.width = 10  # 10 pixels

        pol = kml.newpolygon(name="Shadow",)
        pol.outerboundaryis = [(blong, blat, balt),
                               (elong, elat, ealt),
                               (elong, elat, 0),
                               (blong, blat, 0),
                               (blong, blat, balt)]
        pol.altitudemode = simplekml.AltitudeMode.absolute
        pol.style.polystyle.color = "55000000"

        # kml.save("event.kml")

        output_directory = os.path.dirname(file_path)
        date_time = os.path.basename(file_path)[:16]
        outputfile = os.path.join(
            output_directory, date_time + "3D_track.kml")

        print()
        print("Creating new KML file.....")
        print(outputfile)
        print()

        kml.save(outputfile)
        print("Done!")

    except FileNotFoundError:
        print("The 'report.txt' file was not found.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

else:
    print("No such file")
