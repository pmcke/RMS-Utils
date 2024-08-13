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
import re

def extract_coordinates(file):
    # Initialize variables to store extracted values
    blat, blong, balt = None, None, None
    elat, elong, ealt = None, None, None

    # Define regular expressions for latitude, longitude, and altitude
    # coord_pattern = re.compile(r"[-+]?\d*\.\d+")
    
    # Define patterns for different lines
    lat_pattern = re.compile(r"Lat \(\+N\)\s*=\s*([-+]?\d*\.\d+)")
    lon_pattern = re.compile(r"Lon \(\+E\)\s*=\s*([-+]?\d*\.\d+)")
    ht_pattern = re.compile(r"Ht WGS84\s*=\s*([\d.]+)")



    begin_found = False
    end_found = False

    for line in file:
        if line.strip().startswith('Begin point on the trajectory:'):
            # Extract the beginning coordinates
            begin_found = True
            blat_line = next(file)
            blong_line = next(file)
            balt_line = next(file)
            
            # Search for latitude, longitude, and altitude
            blat_match = lat_pattern.search(blat_line)
            blong_match = lon_pattern.search(blong_line)
            balt_match = ht_pattern.search(balt_line)
            
            if blat_match and blong_match and balt_match:
                blat = float(blat_match.group(1))
                blong = float(blong_match.group(1))
                balt = float(balt_match.group(1))
            else:
                raise ValueError("Failed to extract beginning coordinates.")
        
        if line.strip().startswith('End point on the trajectory:'):
            # Extract the end coordinates
            end_found = True
            elat_line = next(file)
            elong_line = next(file)
            ealt_line = next(file)
            
            # Search for latitude, longitude, and altitude
            elat_match = lat_pattern.search(elat_line)
            elong_match = lon_pattern.search(elong_line)
            ealt_match = ht_pattern.search(ealt_line)
            
            if elat_match and elong_match and ealt_match:
                elat = float(elat_match.group(1))
                elong = float(elong_match.group(1))
                ealt = float(ealt_match.group(1))
            else:
                raise ValueError("Failed to extract end coordinates.")
        
        if begin_found and end_found:
            break

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
            date_time = os.path.basename(file_path)[:16]
            outputfile = os.path.join(output_directory, date_time + "3D_track.kml")

            create_kml(blat, blong, balt, elat, elong, ealt, outputfile)

        except FileNotFoundError:
            print("The 'report.txt' file was not found.")
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    else:
        print("No such file")
