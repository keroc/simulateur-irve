# -*- coding: utf-8 -*-

from coordinates import Coordinates, Polygon, BBox, coord_dist, Line
import sqlite3
import os
import hashlib
import json
from datetime import datetime
import requests

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')
DB_PATH = os.path.join(DATA_PATH, 'data.sqlite')
SIMULATIONS_PATH = os.path.join(DATA_PATH, 'simulations')

GEO_API_URL = "https://geo.api.gouv.fr/communes"
OCM_URL = 'https://api.openchargemap.io/v3/poi'
OCM_APIKEY = 'a37a583e-ed6a-482c-8418-6e3b3d91712a'
IGN_ROUTE_URL = 'https://wxs.ign.fr/calcul/geoportail/itineraire/rest/1.0.0/route'

SSL_VERIFY = False

class SimulationError(Exception):
    """Exception raised for errors in the simulation.

    Attributes:
        step -- simulation step where the error occured
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message

class SimulationArea:
    '''A circle with a center and a radius where the simulation
    will take place'''

    def __init__(self, center=Coordinates(), dist=20, load=None):
        if load is not None:
            self.load(load)
        
        else:
            self.center = center
            self.dist = dist
            
            # Build the id
            hash = hashlib.sha256("{:f}".format(self.center.lon).encode())
            hash.update("{:f}".format(self.center.lat).encode())
            hash.update("{:d}".format(self.dist).encode())
            self.id = hash.hexdigest()

            # Try to load an existing simulation
            try:
                self.load(self.id)
            except:
                # The simulation does not exist, start a new one
                self.cities = []
                self.charging_sites = []
                self.workfluxes = []
                self.tmja = []
                self.cities_duration = {}
                self.sites_duration = {}
    
    def save(self):
        with open(os.path.join(SIMULATIONS_PATH, '{}.json'.format(self.id)), mode='w', encoding="utf-8") as file:
            json.dump(self.to_dict(), file)

    def load(self, id):
        with open(os.path.join(SIMULATIONS_PATH, '{}.json'.format(id)), mode='r', encoding="utf-8") as file:
            temp = json.load(file)

            # General
            self.id = temp['id']
            self.center = Coordinates(lat=temp['lat'], lon=temp['lon'])
            self.dist = temp['dist']

            # Cities
            self.cities = [City(dico=c) for c in temp['cities']]

            # Charging sites
            self.charging_sites = [ChargeSite(dico=s) for s in temp['sites']]

            # Workflux
            self.workfluxes = [TrafficFlow(dico=w) for w in temp['workflux']]

            #  TMJA
            self.tmja = [TrafficFlow(dico=t) for t in temp['tmja']]

            # Durations
            self.cities_duration = temp['cities_duration']
            self.sites_duration = temp['sites_duration']


    def bbox(self):
        return BBox(center=self.center, dist=self.dist)
    
    def to_dict(self):
        # General
        res = {'id': self.id, 'lat': self.center.lat, 'lon': self.center.lon, 'dist': self.dist}

        # Cities
        res['cities'] = [c.to_dict() for c in self.cities]

        # Charging sites
        res['sites'] = [s.to_dict() for s in self.charging_sites]

        # Workflux
        res['workflux'] = [w.to_dict() for w in self.workfluxes]

        # TMJA
        res['tmja'] = [t.to_dict() for t in self.tmja]

        # Durations
        res['cities_duration'] = self.cities_duration
        res['sites_duration'] = self.sites_duration

        return res

    def duration_from_center(self, poi):
        # Get back the itinary from data.gouv and do the real math
        r = requests.get(IGN_ROUTE_URL, params={'resource': 'bdtopo-osrm',
                                                'start': '{:f},{:f}'.format(self.center.lon, self.center.lat),
                                                'end': '{:f},{:f}'.format(poi.lon, poi.lat),
                                                'profile' : 'car',
                                                'getSteps': 'false',
                                                'getBbox': 'false',
                                                'optimization' : 'fastest',
                                                'timeUnit': 'minute',
                                                'distanceUnit': 'kilometer'}, verify=SSL_VERIFY)
        res = r.json()
        if 'error' in res:
            # Backup with dirty calculation
            return Line([self.center, poi]).length() / 20
        
        return res['duration']
    
    def get_cities(self):
        '''Get back all cities in the area'''
        
        # If cities have been loaded, skip the search
        if len(self.cities) > 0:
            return self.cities
        
        # As a first step, we build a bbox and get all cities inside it to go fast
        bbox = self.bbox()
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        
        cur = con.cursor()
        cur.execute('''SELECT 
                    cities.name AS name,
                    cities.insee AS insee,
                    cities.department AS department,
                    cities.population AS population,
                    cities.center_lat AS center_lat,
                    cities.center_lon AS center_lon,
                    cities.mairie_lat AS mairie_lat,
                    cities.mairie_lon AS mairie_lon,
                    cars.nb_vp_el AS nb_vp_el,
                    cars.nb_vp AS nb_vp
                    FROM cities JOIN cars ON cities.insee=cars.insee
                    WHERE
                    center_lat BETWEEN {:f} AND {:f} AND
                    center_lon BETWEEN {:f} AND {:f};'''.format(bbox.min_lat, bbox.max_lat, bbox.min_lon, bbox.max_lon))

        # Clean cities outside the circle
        self.cities = []
        for row in cur:
            city = City(sqlite_row=row)
            if (coord_dist(city.center, self.center) <= self.dist):
                city.get_api_data()
                self.cities.append(city)
                self.cities_duration[city.insee] = self.duration_from_center(city.mairie)

        cur.close()

        # Save for later
        self.save()

        return self.cities

    def get_charging_sites(self):
        '''Get back all charging sites in the area'''
        
        # If charging sites have been loaded, skip the search
        if len(self.charging_sites) > 0:
            return self.charging_sites

        # Get back the sites from open charge map
        r = requests.get(OCM_URL, params={'key': OCM_APIKEY,
                                        'latitude': self.center.lat,
                                        'longitude': self.center.lon,
                                        'distance': self.dist,
                                        'distanceunit': 'km'}, verify=SSL_VERIFY)
        for site in r.json() :
            c = ChargeSite(ocm_json=site)

            # Compute all deviations for this charging site
            for wf in self.workfluxes:
                c.add_deviation(wf)
            for t in self.tmja:
                c.add_deviation(t)

            self.charging_sites.append(c)
            self.sites_duration[c.id] = self.duration_from_center(c.coord)

        # Save for later
        self.save()
        
        return self.charging_sites


    def get_workfluxes(self):
        '''Get back all workfluxes in the area'''
        
        # If charging sites have been loaded, skip the search
        if len(self.workfluxes) > 0:
            return self.workfluxes
        
        # Open a connection
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Get back the workflux for our 
        insee_list = '("{}")'.format('", "'.join([c.insee for c in self.cities]))
        cur.execute('''SELECT * FROM workflux WHERE
                    insee_home IN {} AND
                    insee_work IN {}'''.format(insee_list, insee_list))
        
        # Make it more friendly to use
        table = {}
        for row in cur:
            if not row['insee_home'] in table:
                table[row['insee_home']] = {}
            table[row['insee_home']][row['insee_work']] = row['nb_workers']

        cur.close()
        
        # Loop through all combinaisons
        for idx, c1 in enumerate(self.cities):
            for c2 in self.cities[idx+1:]:
                try:
                    f12 = table[c1.insee][c2.insee]
                    f21 = table[c2.insee][c1.insee]
                    traffic = round(f12 * c1.nb_elec_cars / c1.nb_cars + f21 * c2.nb_elec_cars / c2.nb_cars)
                except:
                    traffic = 0

                # Only append non zero to make it clean
                if traffic > 0:
                    w = TrafficFlow(id='{}-{}'.format(c1.insee, c2.insee),
                                    name='{} - {}'.format(c1.name, c2.name),
                                    itinary=Line([c1.mairie, c2.mairie]),
                                    traffic=traffic)
                    w.enhance_details()
                    self.workfluxes.append(w)
        
        # Save for later
        self.save()
        
        return self.workfluxes
    
    def get_tmja(self):
        '''Get back all TMJA in the area'''
        
        # If TMJA have been loaded, skip the search
        if len(self.tmja) > 0:
            return self.tmja
        
        # As a first step, we build a bbox and get all cities inside it to go fast
        bbox = self.bbox()
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute('''SELECT * FROM tmja WHERE
                    (start_lat BETWEEN {:f} AND {:f} AND
                    start_lon BETWEEN {:f} AND {:f}) AND
                    (end_lat BETWEEN {:f} AND {:f} AND
                    end_lon BETWEEN {:f} AND {:f});'''.format(bbox.min_lat, bbox.max_lat, bbox.min_lon, bbox.max_lon,
                                                              bbox.min_lat, bbox.max_lat, bbox.min_lon, bbox.max_lon))
        
        routes = {}
        # Build all routes
        for rec in cur:
            start_coord = Coordinates(lat=rec['start_lat'], lon=rec['start_lon'])
            end_coord = Coordinates(lat=rec['end_lat'], lon=rec['end_lon'])

            # Clean point outside the area
            if (coord_dist(start_coord, self.center) > self.dist) or (coord_dist(end_coord, self.center) > self.dist):
                continue

            if not rec['route'] in routes:
                routes[rec['route']] = {}
            
            # Add the portion
            routes[rec['route']][rec['cumul_start']] = {'start': start_coord,
                                                        'end': end_coord,
                                                        'tmja': rec['tmja'],
                                                        'ratio_pl': rec['ratio_pl']}
        
        # Build all traffics
        for r, data in routes.items():
            coords = []
            traffic_weight = 0
            total_km = 0

            # Sort the route by cumul_start
            for idx, (_, v) in enumerate(sorted(data.items(), key=lambda item: item[0])):
                coords.append(v['start'])
                if idx+1 == len(data):
                    # We are at the end of the route, add the end
                    coords.append(v['end'])
            
                if v['tmja'] >0:
                    dist = Line(coords=[v['start'], v['end']]).length()
                    traffic_weight += v['tmja'] * dist
                    total_km += dist
            
            # Get the average traffic
            try:
                average = round(traffic_weight / total_km)
            except:
                average = 0
            
            # Create the itinary
            if average > 0:
                t = TrafficFlow(id=r, name=r, itinary=Line(coords), traffic=average)
                t.enhance_details()
                self.tmja.append(t)

        cur.close()

        # Save for later
        self.save()
        
        return self.tmja
    
    def get_simulation_site(self):
        # Build a dummy charging site
        c = ChargeSite()

        # Put default values
        c.max_power = 22
        c.coord = self.center

        # Compute all deviations for this charging site
        for wf in self.workfluxes:
            c.add_deviation(wf)
        for t in self.tmja:
            c.add_deviation(t)

        return (c, self.cities_duration, self.sites_duration)

def get_simulation_list():
    res = []

    for filename in os.listdir(SIMULATIONS_PATH):
        desc = {'id': os.path.splitext(filename)[0]}

        # get coordinates and distance
        with open(os.path.join(SIMULATIONS_PATH, filename), mode='r', encoding="utf-8") as file:
            sim = json.load(file)
            desc['lat'] = sim['lat']
            desc['lon'] = sim['lon']
            desc['dist'] = sim['dist']

        desc['date'] = datetime.fromtimestamp(os.stat(os.path.join(SIMULATIONS_PATH, filename)).st_mtime).strftime('%d/%m/%Y %H:%M:%S')

        res.append(desc)
    
    return res

def delete_simulation(id):
    os.remove(os.path.join(SIMULATIONS_PATH, '{}.json'.format(id)))
    return {'result': 'ok'}

class City:
    """A French city"""

    def __init__(self, sqlite_row=None, dico=None):
        if sqlite_row is not None:
            # Use data from DB
            self.center = Coordinates(lat=sqlite_row['center_lat'], lon=sqlite_row['center_lon'])
            self.mairie = Coordinates(lat=sqlite_row['mairie_lat'], lon=sqlite_row['mairie_lon'])
            self.contour = Polygon()
            self.insee = sqlite_row['insee']
            self.name = sqlite_row['name']
            self.department = sqlite_row['department']
            self.population = sqlite_row['population']
            self.nb_elec_cars = sqlite_row['nb_vp_el']
            self.nb_cars = sqlite_row['nb_vp']
            self.time_to_center = 0.0
        
        elif dico is not None:
            self.from_dict(dico)
        
        else:
            # Default values
            self.center = Coordinates()
            self.mairie = Coordinates()
            self.contour = Polygon()
            self.insee = ''
            self.name = "Unknown"
            self.department = ''
            self.population = 0
            self.nb_elec_cars = 0
            self.nb_cars = 0
            self.time_to_center = 0.0
    
    def from_dict(self, d):
        self.center = Coordinates(geojson=d['center'])
        self.mairie = Coordinates(geojson=d['mairie'])
        self.contour = Polygon(geojson=d['contour'])
        self.insee = d['insee']
        self.name = d['name']
        self.department = d['department']
        self.population = d['population']
        self.nb_elec_cars = d['nb_elec_cars']
        self.nb_cars = d['nb_cars']
        self.time_to_center = d['time_to_center']

    def to_dict(self):
        return {
            'center': self.center.geojsonify(),
            'mairie': self.mairie.geojsonify(),
            'contour': self.contour.geojsonify(),
            'insee': self.insee,
            'name': self.name,
            'department': self.department,
            'population': self.population,
            'nb_elec_cars': self.nb_elec_cars,
            'nb_cars': self.nb_cars,
            'time_to_center': self.time_to_center
        }
    
    def geojsonify(self, geometry='center'):
        geo = {}

        if geometry == 'center':
            geo = self.center.geojsonify()
        elif geometry == 'mairie':
            geo = self.mairie.geojsonify()
        elif geometry == 'contour':
            geo = self.contour.geojsonify()
        else:
            raise SimulationError('Unknown geometry "{}"'.format(geometry))
        
        return {'type': 'Feature', 'properties': {
            'insee': self.insee,
            'name': self.name,
            'department': self.department,
            'population': self.population,
            'nb_elec_cars': self.nb_elec_cars,
            'nb_cars': self.nb_cars,
            'time_to_center': self.time_to_center
        }, 'geometry': geo}
    
    def get_api_data(self):
        # Get back the commune from data.gouv
        r = requests.get(GEO_API_URL + '/' + str(self.insee), params={'format': 'json',
                                                'fields': 'contour,population'}, verify=SSL_VERIFY)
        res = r.json()
        if res is not None :
                self.contour = Polygon(geojson=res['contour'])
                self.population = int(res['population'])
    
        
class TrafficFlow():
    '''A car flow between two cities'''

    def __init__(self, id='', name='Unknown', itinary=Line(), traffic=0, time=0, dico=None):
        if dico is not None:
            self.from_dict(dico)
            return

        self.id = id
        self.name = name
        self.traffic = traffic
        self.itinary = itinary
        self.length = self.itinary.length()
        self.time = time
    
    def load_cities(self, city1, city2, flux12, flux21):
        self.id = '{}-{}'.format(city1.insee, city2.insee)
        self.name = '{} - {}'.format(city1.name, city2.name)

        self.traffic = round(flux12 * city1.nb_elec_cars / city1.nb_cars + flux21 * city2.nb_elec_cars / city2.nb_cars)

        # Finally get the itinary to go from one point to another
        self.itinary = Line([city1.mairie, city2.mairie])
        self.length = self.itinary.length()
        self.time = 60 * 50 / self.length
        
    
    def enhance_details(self):
        # Get back the itinary from data.gouv
        r = requests.get(IGN_ROUTE_URL, params={'resource': 'bdtopo-osrm',
                                                'start': '{:f},{:f}'.format(self.itinary.coords[0].lon, self.itinary.coords[0].lat),
                                                'end': '{:f},{:f}'.format(self.itinary.coords[-1].lon, self.itinary.coords[-1].lat),
                                                'intermediates': '|'.join(['{:f},{:f}'.format(p.lon, p.lat) for p in self.itinary.coords[1:-2]]),
                                                'profile' : 'car',
                                                'optimization' : 'fastest',
                                                'timeUnit': 'minute',
                                                'distanceUnit': 'kilometer'}, verify=SSL_VERIFY)
        res = r.json()
        if not 'error' in res:
            self.itinary = Line(geojson=res['geometry'])
            self.time = res['duration']
            self.length = res['distance']


    def deviation_duration(self, poi, dirty=True):
        if not dirty:
            # Get back the itinary from data.gouv and do the real math
            r = requests.get(IGN_ROUTE_URL, params={'resource': 'bdtopo-osrm',
                                                    'start': '{:f},{:f}'.format(self.itinary.coords[0].lon, self.itinary.coords[0].lat),
                                                    'end': '{:f},{:f}'.format(self.itinary.coords[-1].lon, self.itinary.coords[-1].lat),
                                                    'intermediates': '{:f},{:f}'.format(poi.lon, poi.lat),
                                                    'profile' : 'car',
                                                    'getSteps': 'false',
                                                    'getBbox': 'false',
                                                    'optimization' : 'fastest',
                                                    'timeUnit': 'minute',
                                                    'distanceUnit': 'kilometer'}, verify=SSL_VERIFY)
            res = r.json()
            if not 'error' in res:
                return res['duration'] - self.time
        
        # For performance do it quicker
        speed = 35
        dist = self.itinary.smallest_distance(poi)

        return 2 * 60 * dist / speed



    def geojsonify(self):
        return {'type': 'Feature',
               'properties': {
                   'id': self.id,
                   'name': self.name,
                   'traffic': self.traffic,
                   'time': self.time,
                   'length': self.length
               },
               'geometry': self.itinary.geojsonify()}
    
    def to_dict(self):
        return {'id': self.id,
                'name': self.name,
                'traffic': self.traffic,
                'length': self.length,
                'time': self.time,
                'itinary': self.itinary.geojsonify()}
    
    def from_dict(self, d):
        self.id = d['id']
        self.name = d['name']
        self.traffic = d['traffic']
        self.time = d['time']
        self.length = d['length']
        self.itinary = Line(geojson=d['itinary'])
    
        

class ChargeSite:
    """A Charge site with severals charging station"""

    def __init__(self, ocm_json=None, dico=None):
        if dico is not None:
            self.from_dict(dico)
            return
        
        self.id = ''
        self.cost_text = ''
        self.coord = Coordinates()
        self.name = 'Unkwown'
        self.nb_points = 0
        self.cpo = ''
        self.data_source = ''
        self.max_power = 0
        self.deviations = {}

        try:
            if ocm_json is not None:
                self.id = ocm_json['ID']

                if ocm_json['UsageCost'] is not None:
                    self.cost_text = ocm_json['UsageCost'].replace('\\"', '').replace('"', '')

                self.coord = Coordinates(lat=ocm_json['AddressInfo']['Latitude'], lon=ocm_json['AddressInfo']['Longitude'])
                self.name = ocm_json['AddressInfo']['Title'].replace('\\"', '').replace('"', '')

                self.nb_points = ocm_json['NumberOfPoints']

                if ocm_json['OperatorInfo'] is not None:
                    self.cpo = ocm_json['OperatorInfo']['Title'].replace('\\"', '').replace('"', '')
                
                if ocm_json['DataProvider'] is not None:
                    self.data_source = ocm_json['DataProvider']['Title'].replace('\\"', '').replace('"', '')

                for c in ocm_json['Connections']:
                    if c['PowerKW'] > self.max_power:
                        self.max_power = c['PowerKW']
        
        except:
            pass
            
    def from_dict(self, d):
        self.id = d['id']
        self.cost_text = d['cost']
        self.coord = Coordinates(geojson=d['coord'])
        self.name = d['name']
        self.nb_points = d['nb_points']
        self.cpo = d['cpo']
        self.data_source = d['data_source']
        self.max_power = d['max_power']
        self.deviations = d['deviations']

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'cost': self.cost_text,
            'nb_points': self.nb_points,
            'max_power': self.max_power,
            'cpo': self.cpo,
            'data_source': self.data_source,
            'coord': self.coord.geojsonify(),
            'deviations': self.deviations
        }
    
    def geojsonify(self):
        return {'type': 'Feature',
               'properties': {
                   'id': self.id,
                   'name': self.name,
                   'cost': self.cost_text,
                   'nb_points': self.nb_points,
                   'max_power': self.max_power,
                   'cpo': self.cpo,
                   'data_source': self.data_source,
                   'deviations': self.deviations
               },
               'geometry': self.coord.geojsonify()}

    def add_deviation(self, traffic_flow):
        self.deviations[traffic_flow.id] = traffic_flow.deviation_duration(self.coord)
