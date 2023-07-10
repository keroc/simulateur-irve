# -*- coding: utf-8 -*-

import math

R = 6371 # Earth Radius in km

def deg2rad(deg):
    return deg * math.pi / 180

def rad2deg(rad):
    return rad * 180 / math.pi

def coord_dist(c1, c2):    
    d_lat = deg2rad(c2.lat - c1.lat)
    d_lon = deg2rad(c2.lon - c1.lon)

    # Copy paste of a formula on Google TBH
    a = math.pow(math.sin(d_lat/2), 2) + math.cos(deg2rad(c1.lat)) * math.cos(deg2rad(c2.lat)) * math.pow(math.sin(d_lon/2), 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


class Coordinates:
    """Coordinates used in the configurator"""

    def __init__(self, lat=47.0, lon=0.0, geojson=None):
        self.lat = lat
        self.lon = lon

        if geojson is not None:
            # Build coordinates from a geojeson point
            if geojson["type"] == "Point":
                self.lon = geojson["coordinates"][0]
                self.lat = geojson["coordinates"][1]
    
    def geojsonify(self):
        return {'type':'Point','coordinates':[self.lon,self.lat]}

class BBox:
    '''A boundary box to help filter in a dedicated area'''
    def __init__(self, c1=None, c2=None, center=None, dist=None):
        if c1 is not None and c2 is not None:
            # Init using 2 points
            if c1.lat > c2.lat:
                self.min_lat = c2.lat
                self.max_lat = c1.lat
            else:
                self.min_lat = c1.lat
                self.max_lat = c2.lat

            if c1.lon > c2.lon:
                self.min_lon = c2.lon
                self.max_lon = c1.lon
            else:
                self.min_lon = c1.lon
                self.max_lon = c2.lon

        elif center is not None and dist is not None:
            # Init using a center and a distance (in km)

            # Compute latitude north and south
            delta_lat = rad2deg(dist / R)
            self.min_lat = center.lat - delta_lat
            self.max_lat = center.lat + delta_lat

            # Compute longitude west and east using the north latitude
            radius_lat_min = R * math.sin(deg2rad(90 - self.max_lat))
            delta_lon = rad2deg(dist / radius_lat_min)
            self.min_lon = center.lon - delta_lon
            self.max_lon = center.lon + delta_lon
        
        else:
            # Init with a null BBox
            self.min_lat = 0.0
            self.max_lat = 0.0
            self.min_lon = 0.0
            self.max_lon = 0.0
    
    def is_inside(self, c):
        return self.min_lat <= c.lat and c.lat <= self.max_lat and self.min_lon <= c.lon and c.lon <= self.max_lon

class Polygon:
    """A polygon made of several arrays of coordinates"""
    def __init__(self, coords=[[]], geojson=None):
        self.coords = coords

        if geojson is not None:
            if geojson["type"] == "Polygon":
                self.coords = []

                for pol in geojson["coordinates"] :
                    temp = []
                    for c in pol:
                        temp.append(Coordinates(lon=c[0], lat=c[1]))
                    self.coords.append(temp)
    
    def geojsonify(self):
        res = {'type':'Polygon','coordinates':[]}

        for pol in self.coords:
            temp = []
            for c in pol:
                temp.append([c.lon,c.lat])
            res['coordinates'].append(temp)

        return res

class Line:
    """A line that goes through several coordinates"""
    def __init__(self, coords = [], geojson=None):
        self.coords = coords

        if geojson is not None:
            if geojson["type"] == "LineString":
                self.coords = []

                for c in geojson["coordinates"] :
                    self.coords.append(Coordinates(lon=c[0], lat=c[1]))
    
    def geojsonify(self):
        res = {'type':'LineString','coordinates':[]}

        for c in self.coords:
            res['coordinates'].append([c.lon, c.lat])

        return res

    def length(self):
        res = 0.0

        prev = None
        for c in self.coords:
            if prev is not None:
                res += coord_dist(prev, c)
            prev = c

        return res
    
    def smallest_distance(self, c):
        if len(self.coords) == 0:
            return 0

        return min([Line(coords=[p, c]).length() for p in self.coords])



