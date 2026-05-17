from flask import Flask, render_template, request, jsonify
import requests
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import time
from concurrent.futures import ThreadPoolExecutor
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Keys
ORS_API_KEY = os.getenv('ORS_API_KEY')

# Create a session with improved retry logic
session = requests.Session()
retry = Retry(
    total=2,
    backoff_factor=0.1,
    status_forcelist=[500, 502, 503, 504],
)
adapter = HTTPAdapter(
    max_retries=retry, 
    pool_connections=20, 
    pool_maxsize=20,
    pool_block=False
)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Thread pool for parallel operations
executor = ThreadPoolExecutor(max_workers=10)

# Cache with timeout
class TimedCache:
    def __init__(self, timeout=300):  # 5 minutes
        self.cache = {}
        self.timeout = timeout
    
    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.timeout:
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())

coordinates_cache = TimedCache()
eta_cache = TimedCache()

def clean_place_query(place):
    """
    Nominatim struggles with very long autocomplete strings like
    'Right Bhusari Colony, Pune, Pune City Subdistrict, Pune District, Maharashtra, 411038, India'
    Trim to the first 4 meaningful parts to improve match rate.
    """
    parts = [p.strip() for p in place.split(',')]
    # Remove pure numeric parts (PIN codes) and overly generic admin parts
    filtered = [p for p in parts if p and not p.isdigit()]
    # Keep first 4 parts at most
    return ', '.join(filtered[:4])

def get_coordinates(place):
    """Get latitude and longitude from a place name using OpenStreetMap"""
    if not place or len(place.strip()) < 2:
        return None, None
        
    cached = coordinates_cache.get(place)
    if cached:
        return cached
    
    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        'User-Agent': 'SmartAlarmApp/1.0',
        'Accept': 'application/json',
        'Accept-Language': 'en'
    }
    
    # Try queries from most specific to least specific
    queries_to_try = [place, clean_place_query(place)]
    # Deduplicate while preserving order
    seen = set()
    queries_to_try = [q for q in queries_to_try if q not in seen and not seen.add(q)]

    for query in queries_to_try:
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1,
            'countrycodes': 'in',
        }
        try:
            logger.info(f"Trying geocode query: '{query}'")
            response = session.get(url, params=params, headers=headers, timeout=5)
            logger.info(f"Coordinates API response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    coordinates_cache.set(place, (lat, lon))
                    logger.info(f"Found coordinates for '{query}': ({lat}, {lon})")
                    return lat, lon
                else:
                    logger.warning(f"No results for query: '{query}', trying fallback...")
            else:
                logger.warning(f"Nominatim API returned status {response.status_code} for '{query}'")
        except requests.exceptions.Timeout:
            logger.error(f"Timeout getting coordinates for '{query}'")
        except Exception as e:
            logger.error(f"Error getting coordinates for '{query}': {str(e)}")
    
    logger.error(f"All geocoding attempts failed for place: '{place}'")
    return None, None

def apply_traffic_factor(base_eta, distance_km):
    """Apply realistic traffic factors based on distance and time of day"""
    # Base traffic multiplier (more traffic during rush hours)
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    # Rush hour multipliers
    if (7 <= hour <= 9) or (16 <= hour <= 18):  # Morning and evening rush hours
        rush_multiplier = 1.3  # 30% longer during rush hours
    elif (12 <= hour <= 13):  # Lunch time
        rush_multiplier = 1.15  # 15% longer
    else:
        rush_multiplier = 1.0
    
    # Distance-based factors (shorter trips have more variable traffic)
    if distance_km < 5:
        distance_factor = 1.2  # 20% more time for short urban trips
    elif distance_km < 20:
        distance_factor = 1.1  # 10% more for medium trips
    else:
        distance_factor = 1.05  # 5% more for long trips
    
    # Day of week factor (weekends vs weekdays)
    if weekday >= 5:  # Weekend
        day_factor = 0.9  # 10% less time on weekends
    else:
        day_factor = 1.0
    
    adjusted_eta = base_eta * rush_multiplier * distance_factor * day_factor
    
    # Ensure we don't reduce time too much
    return max(base_eta * 0.9, adjusted_eta)

def get_eta_ors(start_coords, end_coords):
    """Get realistic travel time using OpenRouteService"""
    if not ORS_API_KEY:
        logger.warning("OpenRouteService API key not found, using basic OSRM")
        return get_eta_basic(start_coords, end_coords)
    
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    
    headers = {
        'Authorization': ORS_API_KEY,
        'Content-Type': 'application/json'
    }
    
    body = {
        "coordinates": [
            [start_coords[1], start_coords[0]],  # [lon, lat]
            [end_coords[1], end_coords[0]]
        ],
        "instructions": False,
        "preference": "recommended",
        "units": "km"
    }
    
    try:
        response = session.post(url, json=body, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'routes' in data and data['routes']:
                route = data['routes'][0]
                duration_seconds = route['summary']['duration']
                distance_meters = route['summary']['distance']
                
                duration_minutes = duration_seconds / 60
                distance_km = distance_meters / 1000
                
                logger.info(f"ORS ETA: {duration_minutes:.1f} minutes, Distance: {distance_km:.1f} km")
                
                # Add traffic factor based on urban density and time of day
                adjusted_eta = apply_traffic_factor(duration_minutes, distance_km)
                logger.info(f"Adjusted ETA with traffic factor: {adjusted_eta:.1f} minutes")
                
                return adjusted_eta
            else:
                logger.warning(f"ORS API returned no routes: {data}")
        else:
            logger.warning(f"ORS API HTTP error: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Error getting ORS ETA: {str(e)}")
    
    # Fallback to basic OSRM if ORS fails
    return get_eta_basic(start_coords, end_coords)

def get_eta_basic(start_coords, end_coords):
    """Basic OSRM fallback"""
    cache_key = f"{start_coords[0]},{start_coords[1]}|{end_coords[0]},{end_coords[1]}"
    
    cached = eta_cache.get(cache_key)
    if cached:
        return cached
    
    url = "http://router.project-osrm.org/route/v1/driving/"
    coords_str = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    params = {
        'overview': 'false', 
        'alternatives': 'false',
        'steps': 'false'
    }
    
    try:
        response = session.get(url + coords_str, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 'Ok' and data.get('routes'):
                duration = data['routes'][0]['duration'] / 60
                # Apply basic traffic factor to OSRM results too
                adjusted_duration = duration * 1.15  # Add 15% for basic traffic
                eta_cache.set(cache_key, adjusted_duration)
                return adjusted_duration
    except Exception as e:
        logger.error(f"OSRM error: {str(e)}")
    
    return None

def get_eta_graphhopper(start_coords, end_coords):
    """GraphHopper as an alternative free service"""
    url = "https://graphhopper.com/api/1/route"
    
    params = {
        'point': [f"{start_coords[0]},{start_coords[1]}", f"{end_coords[0]},{end_coords[1]}"],
        'vehicle': 'car',
        'key': 'demo_key',  # Free demo key
        'type': 'json',
        'instructions': 'false',
        'calc_points': 'false'
    }
    
    try:
        response = session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'paths' in data and data['paths']:
                duration_seconds = data['paths'][0]['time'] / 1000  # ms to seconds
                distance_meters = data['paths'][0]['distance']
                
                duration_minutes = duration_seconds / 60
                distance_km = distance_meters / 1000
                
                logger.info(f"GraphHopper ETA: {duration_minutes:.1f} minutes, Distance: {distance_km:.1f} km")
                
                # Apply traffic factors
                adjusted_eta = apply_traffic_factor(duration_minutes, distance_km)
                return adjusted_eta
    except Exception as e:
        logger.warning(f"GraphHopper error: {str(e)}")
    
    return None

def get_eta_with_fallback(start_coords, end_coords):
    """Try multiple free services in order of preference"""
    services = [
        ('OpenRouteService', get_eta_ors),
        ('GraphHopper', get_eta_graphhopper),
        ('OSRM', get_eta_basic)
    ]
    
    for service_name, service_func in services:
        try:
            logger.info(f"Trying {service_name}...")
            eta = service_func(start_coords, end_coords)
            if eta and eta > 0:
                logger.info(f"✓ {service_name} succeeded: {eta:.1f} minutes")
                return eta
        except Exception as e:
            logger.warning(f"✗ {service_name} failed: {str(e)}")
            continue
    
    logger.error("All routing services failed")
    return None

def validate_time_input(time_str):
    """Validate time input format"""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False

@app.route('/')
def index():
    """Main route that serves the HTML page"""
    logger.info("Serving index page")
    return render_template('index.html')

@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    """Autocomplete endpoint for location suggestions"""
    query = request.args.get('q', '').strip()
    logger.info(f"Autocomplete request for: '{query}'")
    
    if not query or len(query) < 2:
        return jsonify([])
    
    url = "https://nominatim.openstreetmap.org/search"
    # Bias results toward Pune — append city context if not already present
    if 'pune' not in query.lower() and 'india' not in query.lower():
        biased_query = f"{query}, Pune, India"
    else:
        biased_query = query
    params = {
        'format': 'json',
        'q': biased_query,
        'limit': 5,
        'addressdetails': 0,
        'countrycodes': 'in',
    }
    
    headers = {
        'User-Agent': 'SmartAlarmApp/1.0',
        'Accept': 'application/json'
    }
    
    try:
        start_time = time.time()
        response = session.get(url, params=params, headers=headers, timeout=3)
        
        if response.status_code == 200:
            places = response.json()
            suggestions = []
            
            for place in places:
                display_name = place.get("display_name", "")
                # Simplify display name for autocomplete
                parts = display_name.split(", ")
                if len(parts) > 3:
                    short_name = ", ".join(parts[:3])
                else:
                    short_name = display_name
                
                suggestions.append({
                    "display_name": short_name,
                    "full_name": display_name
                })
            
            logger.info(f"Autocomplete for '{query}' found {len(suggestions)} results in {time.time()-start_time:.2f}s")
            return jsonify(suggestions)
            
    except requests.exceptions.Timeout:
        logger.warning(f"Autocomplete timeout for: {query}")
    except Exception as e:
        logger.error(f"Autocomplete error for {query}: {str(e)}")
    
    return jsonify([])

@app.route('/calculate', methods=['POST'])
def calculate():
    """Calculate the alarm time based on inputs"""
    start_time = time.time()
    logger.info("Calculate endpoint called")
    
    try:
        # Get form data
        arrival_time_str = request.form.get('arrival_time', '').strip()
        getting_ready_min = request.form.get('getting_ready', '').strip()
        start_place = request.form.get('start_place', '').strip()
        end_place = request.form.get('end_place', '').strip()
        current_alarm = request.form.get('current_alarm', '').strip()

        logger.info(f"Form data - arrival: {arrival_time_str}, start: {start_place}, end: {end_place}")

        # Validate required fields
        if not all([arrival_time_str, getting_ready_min, start_place, end_place]):
            logger.warning("Missing required fields")
            return jsonify({'error': 'Please fill in all required fields.'})

        # Validate time format
        if not validate_time_input(arrival_time_str):
            logger.warning(f"Invalid time format: {arrival_time_str}")
            return jsonify({'error': 'Invalid arrival time format. Use HH:MM.'})

        # Validate getting ready time
        try:
            getting_ready_min = int(getting_ready_min)
            if getting_ready_min < 1 or getting_ready_min > 240:
                return jsonify({'error': 'Getting ready time must be between 1 and 240 minutes.'})
        except ValueError:
            return jsonify({'error': 'Please enter a valid number for getting ready time.'})

        # Get coordinates
        logger.info(f"Getting coordinates for: {start_place} -> {end_place}")
        start_coords = get_coordinates(start_place)
        end_coords = get_coordinates(end_place)

        logger.info(f"Coordinates - start: {start_coords}, end: {end_coords}")

        if not start_coords or not start_coords[0] or not end_coords or not end_coords[0]:
            missing = []
            if not start_coords or not start_coords[0]: 
                missing.append("start location")
            if not end_coords or not end_coords[0]: 
                missing.append("destination")
            return jsonify({'error': f'Could not find {", ".join(missing)}. Please check the addresses.'})

        # Get realistic ETA
        logger.info("Calculating realistic travel time...")
        eta_min = get_eta_with_fallback(start_coords, end_coords)

        if eta_min is None:
            return jsonify({'error': 'Could not calculate travel time. Please check if both locations are reachable by car.'})

        # Calculate wake-up time with smart safety margin
        base_margin = 15
        # Longer trips need more buffer for traffic variability
        traffic_buffer = min(30, eta_min * 0.25)  # Up to 25% of travel time, max 30min
        safety_margin = base_margin + traffic_buffer
        
        arrival_time = datetime.strptime(arrival_time_str, "%H:%M")
        total_minutes_needed = eta_min + getting_ready_min + safety_margin
        wake_up_time = arrival_time - timedelta(minutes=total_minutes_needed)

        # Handle overnight case
        now = datetime.now()
        if wake_up_time.time() < now.time():
            wake_up_time += timedelta(days=1)

        response_data = {
            'arrival_time': arrival_time.strftime("%H:%M"),
            'getting_ready': getting_ready_min,
            'eta': round(eta_min),
            'margin': round(safety_margin),
            'alarm_time': wake_up_time.strftime("%H:%M"),
            'total_travel_time': round(eta_min + getting_ready_min + safety_margin),
            'realistic_routing': True
        }

        if current_alarm:
            response_data['current_alarm'] = current_alarm

        processing_time = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Request processed successfully in {processing_time}ms")
        
        return jsonify(response_data)
    
    except Exception as e:
        logger.error(f"Unexpected error in calculate: {str(e)}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred. Please try again.'})

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    logger.warning(f"404 error: {request.url}")
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"500 error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Ensure templates and static directories exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
        logger.info("Created templates directory")
    
    if not os.path.exists('static'):
        os.makedirs('static')
        logger.info("Created static directory")
    
    logger.info("Starting Flask application...")
    app.run(debug=True, host='0.0.0.0', port=5001)