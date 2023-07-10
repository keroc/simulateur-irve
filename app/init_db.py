import os
import sqlite3
import shapefile
import argparse
import csv
import datetime
from pyproj import Transformer

####################################################
# HERE ARE SOME HELPERS
####################################################

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'data.sqlite')
transformer = Transformer.from_crs("EPSG:2154", "EPSG:4326")

def lambert_to_lonlat(c):
    return transformer.transform(c[0], c[1])

def progressBar(current, total):
    percent = current / total
    nbBlocs = 40
    filledBlocs = int(nbBlocs * percent)
    if filledBlocs > nbBlocs:
        filledBlocs = nbBlocs
    bar = '█' * filledBlocs + '-' * (nbBlocs-filledBlocs)
    print('Progress: |{}| {:01.1f} %'.format(bar, 100*percent), end='\r')

####################################################
# THE COMMANDS FUNCTION
####################################################

def update_cities_table(folder):
    if not os.path.isdir(folder):
        print('"{}" does not seems to be a directory'.format(folder))
        return
    
    # Open the DB and create the table if needed. We also clear it to make sure it is empty
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS cities (
            id integer PRIMARY KEY,
            name text NOT NULL,
            insee text NOT NULL,
            population integer,
            department text,
            bbox_ul_lat float,
            bbox_ul_lon float,
            bbox_lr_lat float,
            bbox_lr_lon float,
            center_lat float,
            center_lon float,
            mairie_lat float,
            mairie_lon float
    );''')
    cur.execute('DELETE FROM cities')

    #
    # STEP 1 : cities
    #
    print('Reading commune list from the folder...')
    sf = shapefile.Reader(os.path.join(folder, 'COMMUNE'))
    shapeRecs = sf.shapeRecords()
    nbComs = len(shapeRecs)
    print('Nb cities in ADMIN EXPRESS directory : {}'.format(nbComs))
    print('Adding all cities in the DB')

    # Add them in DB
    for idx, sr in enumerate(shapeRecs):
        
        # Transform the BBox with the rights coordinates
        bbox_ul = lambert_to_lonlat([sr.shape.bbox[0], sr.shape.bbox[1]])
        bbox_lr = lambert_to_lonlat([sr.shape.bbox[2], sr.shape.bbox[3]])

        cur.execute('''INSERT INTO cities (name, insee, population, department, bbox_ul_lat, bbox_ul_lon, bbox_lr_lat, bbox_lr_lon, center_lat, center_lon)
                        VALUES ("{}", "{}", {:d}, "{}", {:f}, {:f}, {:f}, {:f}, {:f}, {:f});
                        '''.format(sr.record[1], sr.record[3], int(sr.record[5]), sr.record[8],
                                   bbox_ul[0], bbox_ul[1], bbox_lr[0], bbox_lr[1],
                                   (bbox_ul[0] + bbox_lr[0])/2, (bbox_ul[1] + bbox_lr[1])/2))
        
        # Show the progress time to time
        if (idx % 200) == 0:
            progressBar(idx, nbComs)

    # Commit all at the end
    con.commit()
    progressBar(nbComs, nbComs)
    print()

    #
    # STEP 2 : MAIRIES
    #
    print('Reading mairie list from the folder...')
    sf = shapefile.Reader(os.path.join(folder, 'CHFLIEU_COMMUNE'))
    shapeRecs = sf.shapeRecords()
    nbMairies = len(shapeRecs)
    print('Nb mairies in ADMIN EXPRESS directory : {}'.format(nbMairies))
    print('Adding all mairies in the DB')

    # Add them in DB
    for idx, sr in enumerate(shapeRecs):
        
        # Transform the coordinates
        coord = lambert_to_lonlat(sr.shape.points[0])
        cur.execute('''UPDATE cities
                        SET mairie_lat = {:f}, mairie_lon = {:f}
                        WHERE insee = "{}";
                        '''.format(coord[0], coord[1], sr.record[3]))
        
        # Show the progress time to time
        if (idx % 200) == 0:
            progressBar(idx, nbMairies)
    
    # Commit all at the end
    con.commit()
    progressBar(nbMairies, nbMairies)
    print()

    print('Cities database updated.')

    # Close the DB
    cur.close()


def update_cars_table(filename):
    if not os.path.isfile(filename):
        print('"{}" does not seems to be a file'.format(filename))
        return

    print("Reading the file...")
    records = {}
    with open(filename, encoding="utf-8") as csvfile:
        spamreader = csv.reader(csvfile, delimiter=';')

        # Skip header
        next(spamreader, None)

        for row in spamreader :
            rec = {'nb_vp_el': int(row[5]),
                   'nb_vp': int(row[7]),
                   'date': datetime.datetime.strptime(row[4], '%Y-%m-%d')}
            
            if row[0] in records :
                # Update INSEE if newer
                older = records[row[0]]
                if rec['date'] > older['date']:
                    records[row[0]] = rec

            else:
                # New INSEE
                records[row[0]] = rec


    row_count = len(records)

    # Open the DB and create the table if needed. We also clear it to make sure it is empty
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS cars (
            id integer PRIMARY KEY,
            insee text NOT NULL,
            nb_vp_el integer,
            nb_vp integer
    );''')
    cur.execute('DELETE FROM cars')

    for idx, (insee, rec) in enumerate(records.items()):
            cur.execute('''INSERT INTO cars (insee, nb_vp_el, nb_vp)
                VALUES ("{}", {:d}, {:d});'''.format(insee, int(rec['nb_vp_el']), int(rec['nb_vp'])))
            
            # Show the progress time to time
            if (idx % 200) == 0:
                progressBar(idx, row_count)
    
    # Commit all at the end
    con.commit()
    progressBar(row_count, row_count)
    print()

    print('Cars database updated.')

    # Close the DB
    cur.close()




def update_workflux_table(filename):
    if not os.path.isfile(filename):
        print('"{}" does not seems to be a file'.format(filename))
        return

    print("Reading the file...")
    records = []
    with open(filename, encoding="utf-8") as csvfile:
        spamreader = csv.reader(csvfile, delimiter=';')

        # Skip header
        next(spamreader, None)
        records = [[row[0], row[2], float(row[4])] for row in spamreader]

    row_count = len(records)

    # Open the DB and create the table if needed. We also clear it to make sure it is empty
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS workflux (
            id integer PRIMARY KEY,
            insee_home text NOT NULL,
            insee_work text NOT NULL,
            nb_workers float
    );''')
    cur.execute('DELETE FROM workflux')

    for idx, rec in enumerate(records):
            cur.execute('''INSERT INTO workflux (insee_home, insee_work, nb_workers)
                VALUES ("{}", "{}", {:f});'''.format(rec[0], rec[1], rec[2]))
            
            # Show the progress time to time
            if (idx % 200) == 0:
                progressBar(idx, row_count)
    
    # Commit all at the end
    con.commit()
    progressBar(row_count, row_count)
    print()

    print('Workflux database updated.')

    # Close the DB
    cur.close()


def update_tmja_table(filename):
    if not os.path.isfile(filename):
        print('"{}" does not seems to be a file'.format(filename))
        return

    print("Reading the file...")
    records = []
    with open(filename, encoding="utf-8") as csvfile:
        spamreader = csv.reader(csvfile, delimiter=';')

        # Skip header
        next(spamreader, None)
        # route, cumulD, xD, yD, cumulF, xF, yF,TMJA, ratio_PL
        for row in spamreader:
            rec = [row[1],
                    float(row[7].replace(',','.')),
                    float(row[8].replace(',','.')),
                    float(row[9].replace(',','.')),
                    float(row[15].replace(',','.')),
                    float(row[16].replace(',','.')),
                    float(row[17].replace(',','.'))]
            
            if row[22] == '':
                rec.append(0)
            else:
                rec.append(int(row[22]))
            
            if row[23] == '':
                rec.append(0.0)
            else:
                rec.append(float(row[23].replace(',','.')))
            
            records.append(rec)

    row_count = len(records)

    # Open the DB and create the table if needed. We also clear it to make sure it is empty
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS tmja (
            id integer PRIMARY KEY,
            route text NOT NULL,
            cumul_start float,
            start_lat float,
            start_lon float,
            end_lat float,
            end_lon float,
            tmja int,
            ratio_pl float
    );''')
    cur.execute('DELETE FROM tmja')

    for idx, rec in enumerate(records):
            start_coord = lambert_to_lonlat([rec[2], rec[3]])
            end_coord = lambert_to_lonlat([rec[5], rec[6]])
    
            cur.execute('''INSERT INTO tmja (route, cumul_start, start_lat, start_lon, end_lat, end_lon, tmja, ratio_pl)
                VALUES ("{}", {:f}, {:f}, {:f}, {:f}, {:f}, {:d}, {:f});'''.format(rec[0], rec[1], start_coord[0], start_coord[1], end_coord[0], end_coord[1], rec[7], rec[8]))
            
            # Show the progress time to time
            if (idx % 200) == 0:
                progressBar(idx, row_count)
    
    # Commit all at the end
    con.commit()
    progressBar(row_count, row_count)
    print()

    print('TMJA database updated.')

    # Close the DB
    cur.close()

####################################################
# MAIN ENTRY POINT
####################################################

if __name__ == "__main__":
    # Init command line parser
    parser = argparse.ArgumentParser(description="Update or initialize the application DB")

    # Subparsers depending on what we want to update
    subparsers = parser.add_subparsers(help='commands', dest="command")

    # cities table subparser
    com_parser = subparsers.add_parser("cities")
    com_parser.add_argument('admin_exp_folder', help='folder where all the shapefile are located')

    # Cars table subparser
    car_parser = subparsers.add_parser("cars")
    car_parser.add_argument('cars_file', help='file downloaded from data.gouv')

    # Workflux table subparser
    wf_parser = subparsers.add_parser("workflux")
    wf_parser.add_argument('workflux_file', help='file downloaded from data.gouv')

    # TMJA table subparser
    tmja_parser = subparsers.add_parser("tmja")
    tmja_parser.add_argument('tmja_file', help='file downloaded from data.gouv')

    args = parser.parse_args()

    # Let's go with the corresponding command
    if args.command == 'cities':
        update_cities_table(args.admin_exp_folder)
    elif args.command == 'cars':
        update_cars_table(args.cars_file)
    elif args.command == 'workflux':
        update_workflux_table(args.workflux_file)
    elif args.command == 'tmja':
        update_tmja_table(args.tmja_file)


