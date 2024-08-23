"""
makeKml.py by Peter McKellar with input from Jesse Stayte and ChatGPT. 26 September 2023

After running the trajectory solver, one of the resulting files is a text file with name 
ending in report.txt. This script extracts the beginning lat, long & alt and the end lat, long & alt from that file 
and creates a kml file called Fireball.kml in the same folder as the *report.txt file.

It only has one argument and that is the full path and file name of the *.txt file. That can be obtained in Windows 
by right clicking on the file name and selecting Copy as Path.

With help from OpenAI, this version is flexible, and can extract the data, even if there are slight variations in the format of the report file.

"""
import simplekml
import os
import sys
import re

def extract_coordinates(file):
    # Initialize variables to store extracted values
    blat, blong, balt = None, None, None
    elat, elong, ealt = None, None, None

    # Define regular expressions for latitude, longitude, and altitude
    lat_pattern = re.compile(r"Lat \(\+N\)\s*=\s*([-+]?\d*\.\d+)")
    lon_pattern = re.compile(r"Lon \(\+E\)\s*=\s*([-+]?\d*\.\d+)")
    ht_pattern = re.compile(r"Ht WGS84\s*=\s*([\d.]+)")

    begin_found = False
    end_found = False

    for line in file:
        if "Begin point on the trajectory:" in line:
            begin_found = True

        if begin_found and not blat and lat_pattern.search(line):
            blat = float(lat_pattern.search(line).group(1))
        if begin_found and not blong and lon_pattern.search(line):
            blong = float(lon_pattern.search(line).group(1))
        if begin_found and not balt and ht_pattern.search(line):
            balt = float(ht_pattern.search(line).group(1))

        if "End point on the trajectory:" in line:
            end_found = True

        if end_found and not elat and lat_pattern.search(line):
            elat = float(lat_pattern.search(line).group(1))
        if end_found and not elong and lon_pattern.search(line):
            elong = float(lon_pattern.search(line).group(1))
        if end_found and not ealt and ht_pattern.search(line):
            ealt = float(ht_pattern.search(line).group(1))

        # Stop if both sets of coordinates are found
        if begin_found and end_found and all([blat, blong, balt, elat, elong, ealt]):
            break

    if not all([blat, blong, balt, elat, elong, ealt]):
        raise ValueError("Failed to extract both beginning and end coordinates.")

    return (blat, blong, balt), (elat, elong, ealt)

def create_kml(blat, blong, balt, elat, elong, ealt, outputfile):
    kml = simplekml.Kml()

    coordinates = [(blong, blat, balt), (elong, elat, ealt)]

    lin = kml.newlinestring(name="Fireball")
    lin.coords = coordinates
    lin.altitudemode = simplekml.AltitudeMode.absolute
    lin.style.linestyle.color = simplekml.Color.red  # Red
    lin.style.linestyle.width = 10  # 10 pixels

    pol = kml.newpolygon(name="Shadow")
    pol.outerboundaryis = [(blong, blat, balt),
                           (elong, elat, ealt),
                           (elong, elat, 0),
                           (blong, blat, 0),
                           (blong, blat, balt)]
    pol.altitudemode = simplekml.AltitudeMode.absolute
    pol.style.polystyle.color = "55000000"

    print("Creating new KML file.....")
    kml.save(outputfile)
    print("Done!")

if __name__ == "__main__":
    file_path = sys.argv[1]
    if os.path.isfile(file_path):
        try:
            with open(file_path, 'r') as f:
                (blat, blong, balt), (elat, elong, ealt) = extract_coordinates(f)

            if None in (blat, blong, balt, elat, elong, ealt):
                raise ValueError("Failed to extract coordinates.")

            output_directory = os.path.dirname(file_path)
            date_time = os.path.basename(file_path)[:15]
            outputfile = os.path.join(output_directory, date_time + "3D_track.kml")

            create_kml(blat, blong, balt, elat, elong, ealt, outputfile)

        except FileNotFoundError:
            print("The 'report.txt' file was not found.")
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    else:
        print("No such file")
