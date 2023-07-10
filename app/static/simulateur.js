const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'

// Get back Coordinates from a text address
function geocode(search_str, success, error) {
    $.ajax({
        url: NOMINATIM_URL,
        type: "GET",
        data: {
            q: search_str,
            format: 'json'
        },
        success: function(response) {
            if (response.length == 0) {
                error()
            } else {
                success({lat:response[0].lat, lon:response[0].lon});
            }
        },
        error: error
    });
}

// The big function that handles everything behind the scene
function get_simulation_data(coord, dist, callbacks) {
    var sim_id = '';
    var sim_data = new SimulationData();

    // Helper function to handle callbacks
    function hook(...args) {
        hook_name = args.shift()
        if (hook_name !== undefined && callbacks[hook_name] !== undefined) {
            callbacks[hook_name](...args);
        }
    }

    // Helper function to handle errors from AJAX calls
    function ajax_error(jqXHR, textStatus, errorThrown) {
        hook('error', jqXHR.responseJSON);
    }

    // START
    hook('start');

    // STEP 1 : Create the simulation
    hook('status_text', 'Initialisation de la simulation');
    $.ajax({
        url: '/api/v1/simulations',
        type: "POST",
        data: {
            lat: coord.lat,
            lon: coord.lon,
            dist: dist
        },
        success: function(response) {
            sim_id = response.id;
            hook('area_loaded', response)
            step2();
        },
        error: ajax_error
    });

    // STEP 2 : Get the cities in the simulation area
    function step2() {
        hook('status_text', 'Récupération des villes dans la zone de simulation');
        $.ajax({
            url: `/api/v1/simulations/${sim_id}/cities`,
            type: "GET",
            success: function(response) {
                sim_data.load_cities(response);
                hook('cities_loaded', response);
                step3();
            },
            error: ajax_error
        });
    }

    // STEP 3 : Get the workfluxes in the simulation area
    function step3() {
        hook('status_text', 'Récupération des trajets domicile-travail dans la zone de simulation');
        $.ajax({
            url: `/api/v1/simulations/${sim_id}/workfluxes`,
            type: "GET",
            success: function(response) {
                sim_data.load_workfluxes(response);
                hook('workfluxes_loaded', response);
                step4();
            },
            error: ajax_error
        });
    }

    // STEP 4 : Get the tmja in the simulation area
    function step4() {
        hook('status_text', 'Récupération du traffic routier national dans la zone de simulation');
        $.ajax({
            url: `/api/v1/simulations/${sim_id}/tmja`,
            type: "GET",
            success: function(response) {
                sim_data.load_tmja(response);
                hook('tmja_loaded', response);
                step5();
            },
            error: ajax_error
        });
    }

    // STEP 5 : Get the charging stations in the simulation area
    function step5() {
        hook('status_text', 'Récupération des bornes de recharges dans la zone de simulation');
        $.ajax({
            url: `/api/v1/simulations/${sim_id}/charging_sites`,
            type: "GET",
            success: function(response) {
                sim_data.load_sites(response);
                hook('charging_sites_loaded', response);
                step6();
            },
            error: ajax_error
        });
    }

    // STEP 6 : Get the simulated site in the center of the area
    function step6() {
        hook('status_text', 'Récupération des bornes de recharges dans la zone de simulation');
        $.ajax({
            url: `/api/v1/simulations/${sim_id}/simulation_site`,
            type: "GET",
            success: function(response) {
                sim_data.sim_site = new ChargingSite(response.geojson);
                sim_data.sites_duration = response.sites_duration;
                sim_data.cities_duration = response.cities_duration;
                hook('simulation_site_loaded', response);
                final_step();
            },
            error: ajax_error
        });
    }

    // FINAL STEP : Launch a first simulation
    function final_step() {
        sim_data.simulate();
        hook('simulation_available', sim_data);
        // END OF THE HARD WORK !
        hook('end');
    }
}

// Cities in the area
class City {
    constructor(geojson) {
        this.insee = geojson.properties.insee;
        this.name = geojson.properties.name;
        this.nb_e_cars = geojson.properties.nb_elec_cars;
        this.nb_cars = geojson.properties.nb_cars;
        this.time_to_center = geojson.properties.time_to_center;
    }
}

// Traffic on a road
class TrafficFlow {
    constructor(geojson) {
        this.id = geojson.properties.id;
        this.name = geojson.properties.name;
        this.traffic = geojson.properties.traffic;
        this.dist = geojson.properties.length;
    }
}

// A charging site
class ChargingSite {
    constructor(geojson) {
        this.id = geojson.properties.id;
        this.name = geojson.properties.name;
        this.max_power = geojson.properties.max_power;
        this.deviations = geojson.properties.deviations;
        this.enabled = true;
        this.time_bonus = 0;
    }

    charge_delay_available(tf) {
        return (tf.id in this.deviations) && this.enabled;
    }

    /* 
    * Actually compute the time (in minutes) needed to charge an amount of energy for
    * a car riding on a specific trafic flow. If the cite is attractive, a time bonu is applied
    */
    charge_delay(tf, energy) {
        return this.deviations[tf.id] + Math.max(60 * (energy / this.max_power) - this.time_bonus, 0);
    }
}

class SimulationData {
    constructor() {
        this.sim_site = null;
        this.sites = [];
        this.cities = [];
        this.workfluxes = [];
        this.tmja = [];
        this.cities_duration = {};
        this.sites_duration = {};
        this.parameters = {
            general: {
                charge_energy : 35,
                ratio_home_charge : 0.8,
                ratio_ve_hybrid : 0.63,
                conso_ve : 18.0,
                conso_hybrid : 9.0
            },
            tmja : {
                ratio_ve: 0.02
            },
            local : {
                dist_per_year : 9000,
                time_from_home : 5,
                ratio_home_street : 0.001
            }
        };
        this.stats = {
            local: {},
            workflux: {},
            tmja: {}
        };
        this.results = {
            local: 0.0,
            workflux: 0.0,
            tmja: 0.0
        };
    }

    load_cities(geojson) {
        this.cities = [];

        for (let i=0; i<geojson.features.length; i++) {
            this.cities.push(new City(geojson.features[i]));
        }
    }

    load_workfluxes(geojson) {
        this.workfluxes = [];

        for (let i=0; i<geojson.features.length; i++) {
            this.workfluxes.push(new TrafficFlow(geojson.features[i]));
        }
    }

    load_tmja(geojson) {
        this.tmja = [];

        for (let i=0; i<geojson.features.length; i++) {
            this.tmja.push(new TrafficFlow(geojson.features[i]));
        }
    }

    load_sites(geojson) {
        this.sites = [];

        for (let i=0; i<geojson.features.length; i++) {
            this.sites.push(new ChargingSite(geojson.features[i]));
        }
    }

    captured_traffic(flow) {
        if (!this.sim_site.charge_delay_available(flow)) {
            // no data available
            return 0;
        }

        // Get the score for the simulated site
        let sim_site_delay = this.sim_site.charge_delay(flow, this.parameters.general.charge_energy);
        let sim_site_visible_power = this.parameters.general.charge_energy / (sim_site_delay / 60);
        let sim_site_score = Math.pow(sim_site_visible_power, 2);
        let total_score = sim_site_score;
        
        // Get the score for the others sites
        for (let i=0; i<this.sites.length; i++) {
            if(this.sites[i].charge_delay_available(flow)) {
                let s_delay = this.sites[i].charge_delay(flow, this.parameters.general.charge_energy);
                let s_visible_power = this.parameters.general.charge_energy / (s_delay / 60);
                total_score += Math.pow(s_visible_power, 2);
            }
        }

        return flow.traffic * sim_site_score / total_score;
    }


    simulate() {
        let avg_conso = this.parameters.general.conso_ve * this.parameters.general.ratio_ve_hybrid + this.parameters.general.conso_hybrid * (1-this.parameters.general.ratio_ve_hybrid);

        // Simulate the Local
        this.stats.local.nb_cities = this.cities.length;
        this.stats.local.total_cars = 0.0;
        this.stats.local.total_ev_cars = 0.0;
        this.stats.local.in_range_ev_cars = 0.0;
        this.stats.local.in_range_sites = 0;

        let nb_local_ecars = 0;        
        for (let i=0; i<this.cities.length; i++) {
            this.stats.local.total_cars += this.cities[i].nb_cars;
            this.stats.local.total_ev_cars += this.cities[i].nb_e_cars;
            if(this.cities_duration[this.cities[i].insee] <= this.parameters.local.time_from_home) {
                this.stats.local.in_range_ev_cars += this.cities[i].nb_e_cars;
            }
        }

        for (let s in this.sites_duration) {
            if (this.sites_duration[s] <= this.parameters.local.time_from_home) {
                this.stats.local.in_range_sites += 1;
            }
        }
        
        this.stats.local.total_distance = this.stats.local.in_range_ev_cars * this.parameters.local.dist_per_year;
        this.stats.local.total_energy = this.stats.local.total_distance * avg_conso;
        this.stats.local.street_energy = this.stats.local.total_energy * this.parameters.general.ratio_home_charge * this.parameters.local.ratio_home_street;

        this.results.local = this.stats.local.street_energy / (this.stats.local.in_range_sites+1);

        // Simulate the Worfluxes
        this.stats.workflux.total_ev_traffic = 0.0;
        this.stats.workflux.captured_traffic = 0.0;
        this.stats.workflux.distance = 0.0;
        for (let i=0; i<this.workfluxes.length; i++) {
            this.stats.workflux.total_ev_traffic += 47 * 5 * this.workfluxes[i].traffic;
            let wf_traffic = 47 * 5 * this.captured_traffic(this.workfluxes[i]);
            this.stats.workflux.captured_traffic += wf_traffic;
            this.stats.workflux.distance += wf_traffic * 2 * this.workfluxes[i].dist;
        }
        this.results.workflux = (1-this.parameters.general.ratio_home_charge) * avg_conso * this.stats.workflux.distance / 100;

        // Simulate the TMJA
        this.stats.tmja.total_traffic = 0.0;
        this.stats.tmja.captured_traffic = 0.0;
        this.stats.tmja.distance = 0.0;
        for (let i=0; i<this.tmja.length; i++) {
            this.stats.tmja.total_traffic += this.tmja[i].traffic;
            let captured_traffic = this.captured_traffic(this.tmja[i]);
            this.stats.tmja.captured_traffic += captured_traffic;
            this.stats.tmja.distance += captured_traffic * this.tmja[i].dist;
        }

        this.stats.tmja.total_traffic *= 365;
        this.stats.tmja.total_ev_traffic = this.parameters.tmja.ratio_ve * this.stats.tmja.total_traffic;
        this.stats.tmja.roaming_ev_traffic = Math.max(this.stats.tmja.total_ev_traffic - this.stats.workflux.total_ev_traffic, 0);
        if(this.stats.tmja.total_ev_traffic > 0) {
            this.stats.tmja.captured_traffic *= 365 * this.parameters.tmja.ratio_ve * (this.stats.tmja.roaming_ev_traffic / this.stats.tmja.total_ev_traffic);
            this.stats.tmja.distance *= 365 * this.parameters.tmja.ratio_ve * (this.stats.tmja.roaming_ev_traffic / this.stats.tmja.total_ev_traffic);
        } else {
            this.stats.tmja.captured_traffic = 0;
            this.stats.tmja.distance = 0;
        }

        this.results.tmja = (1-this.parameters.general.ratio_home_charge) * avg_conso * this.stats.tmja.distance / 100;
    }
}