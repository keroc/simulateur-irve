# -*- coding: utf-8 -*-

from flask import Flask, request, render_template, jsonify
from simulation import SimulationArea, SimulationError, get_simulation_list, delete_simulation
from coordinates import Coordinates
from functools import wraps

app = Flask(__name__)

# Small helper
def api_error_handler(func):
    #return func
    
    def error_resp(type, msg):
        return jsonify({'type': type, 'error': msg}), 500
    
    @wraps(func)
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except SimulationError as se:
            return error_resp('simulation', se.msg)
        
        except Exception as e:
            return error_resp('prog', str(e))

    return inner

@app.route("/")
@app.route("/simulateur")
def sim():
    return render_template('simulateur.html')

@app.route("/list")
def listing():
    return render_template('listing.html', sims=get_simulation_list())

#
# API
#

@app.route("/api/v1/simulations", methods=['POST'])
@api_error_handler
def simulation_list_v1():
    if request.method == 'POST':
        # Create a new simulation, save it and return it
        c = Coordinates(lat=float(request.form['lat']), lon=float(request.form['lon']))
        sim = SimulationArea(center=c, dist=int(request.form['dist']))
        sim.save()
        return jsonify(sim.to_dict())

@app.route("/api/v1/simulations/<sim_id>", methods=['DELETE'])
@api_error_handler
def simulation_v1(sim_id):
    if request.method == 'DELETE':
        return delete_simulation(sim_id)

@app.route("/api/v1/simulations/<sim_id>/cities", methods=['GET'])
@api_error_handler
def city_v1(sim_id):
    sim = SimulationArea(load=sim_id)
    return jsonify({'type': 'FeatureCollection', 'features': [c.geojsonify(geometry='contour') for c in sim.get_cities()]})

@app.route("/api/v1/simulations/<sim_id>/workfluxes", methods=['GET'])
@api_error_handler
def workflux_v1(sim_id):
    sim = SimulationArea(load=sim_id)
    return jsonify({'type': 'FeatureCollection', 'features': [w.geojsonify() for w in sim.get_workfluxes()]})

@app.route("/api/v1/simulations/<sim_id>/tmja", methods=['GET'])
@api_error_handler
def tmja_v1(sim_id):
    sim = SimulationArea(load=sim_id)
    return jsonify({'type': 'FeatureCollection', 'features': [t.geojsonify() for t in sim.get_tmja()]})

@app.route("/api/v1/simulations/<sim_id>/charging_sites", methods=['GET'])
@api_error_handler
def charging_sites_v1(sim_id):
    sim = SimulationArea(load=sim_id)
    return jsonify({'type': 'FeatureCollection', 'features': [c.geojsonify() for c in sim.get_charging_sites()]})

@app.route("/api/v1/simulations/<sim_id>/simulation_site", methods=['GET'])
@api_error_handler
def simulation_site_v1(sim_id):
    sim = SimulationArea(load=sim_id)
    (site, cities_dur, sites_dur) = sim.get_simulation_site()
    return jsonify({'geojson': site.geojsonify(),
                    'cities_duration': cities_dur,
                    'sites_duration': sites_dur})
