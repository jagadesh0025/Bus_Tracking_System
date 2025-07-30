from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import Integer
import threading
import time
import math

# --- Firebase Admin ---
import firebase_admin
from firebase_admin import credentials, db as fb_db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bustracking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Initialize Firebase Admin SDK
cred = credentials.Certificate('bus-tracking-system-37edd-firebase-adminsdk-fbsvc-1a9c56672d.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://bus-tracking-system-37edd-default-rtdb.firebaseio.com/'
})

# ------------------- Models -------------------
class Stop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    time_to_next = db.Column(db.Integer)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

class Route(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

class RouteStop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'))
    stop_id = db.Column(db.Integer, db.ForeignKey('stop.id'))
    position = db.Column(Integer)
    stop = db.relationship('Stop')

class Bus(db.Model):
    id = db.Column(db.String(10), primary_key=True)
    current_stop_id = db.Column(db.Integer, db.ForeignKey('stop.id'), nullable=True)
    current_stop = db.relationship('Stop')
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'))
    route = db.relationship('Route')

class BusGPS(db.Model):
    __tablename__ = 'bus_gps'
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.String(10), db.ForeignKey('bus.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float)
    
    bus = db.relationship('Bus', backref=db.backref('gps_updates', lazy=True))

def initialize_database():
    with app.app_context():
        db.create_all()

initialize_database()

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def update_bus_location():
    """Fetch GPS data from Firebase and update DB"""
    while True:
        try:
            with app.app_context():
                gps_data_ref = fb_db.reference('/gpsdata')
                result = gps_data_ref.get()

                if result:
                    lat = result.get('latitude')
                    lng = result.get('longitude')
                    speed = result.get('speedkmph')

                    if None in [lat, lng, speed]:
                        continue

                    bus = db.session.get(Bus, "101")
                    if bus:
                        gps = BusGPS(
                            bus_id="101",
                            latitude=lat,
                            longitude=lng,
                            speed=speed
                        )
                        db.session.add(gps)

                        nearest_stop = None
                        min_distance = float('inf')

                        for stop in Stop.query.all():
                            distance = haversine_distance(lat, lng, stop.latitude, stop.longitude)
                            if distance < 0.2 and distance < min_distance:
                                min_distance = distance
                                nearest_stop = stop

                        if nearest_stop and bus.current_stop_id != nearest_stop.id:
                            bus.current_stop_id = nearest_stop.id
                            print(f"Updated current stop to: {nearest_stop.name}")

                        db.session.commit()

        except Exception as e:
            print(f"Error updating bus location: {e}")

        time.sleep(5)

# Start thread
firebase_thread = threading.Thread(target=update_bus_location)
firebase_thread.daemon = True
firebase_thread.start()

def calculate_arrival_time(bus, user_stop_name):
    if bus.current_stop_id is None:
        return "Waiting for GPS data", ""

    user_stop = Stop.query.filter_by(name=user_stop_name).first()
    if not user_stop:
        return "Invalid stop selection", ""

    route_stops = (RouteStop.query.filter_by(route_id=bus.route_id)
                   .join(Stop)
                   .order_by(RouteStop.position).all())

    stop_names = [rs.stop.name for rs in route_stops]

    try:
        current_index = next(i for i, rs in enumerate(route_stops) if rs.stop_id == bus.current_stop_id)
        user_index = stop_names.index(user_stop_name)
    except (StopIteration, ValueError):
        return "Invalid stop selection", ""

    if user_index < current_index:
        return "The bus has already passed this stop.", ""

    if current_index == user_index:
        return "Arriving now!", "The bus is at your stop"

    latest_gps = BusGPS.query.filter_by(bus_id=bus.id).order_by(BusGPS.id.desc()).first()
    speed = latest_gps.speed if latest_gps and latest_gps.speed else 30

    total_distance = 0
    prev_lat = bus.current_stop.latitude
    prev_lng = bus.current_stop.longitude

    for i in range(current_index + 1, user_index + 1):
        next_stop = route_stops[i].stop
        total_distance += haversine_distance(prev_lat, prev_lng, next_stop.latitude, next_stop.longitude)
        prev_lat = next_stop.latitude
        prev_lng = next_stop.longitude

    if speed > 0:
        time_minutes = (total_distance / speed) * 60
    else:
        time_minutes = sum(rs.stop.time_to_next for rs in route_stops[current_index:user_index])

    arrival_time = datetime.now() + timedelta(minutes=time_minutes)
    return arrival_time.strftime("%I:%M %p"), f"Expected in {int(time_minutes)} minutes"

@app.route('/')
def index():
    bus_stops = [s.name for s in Stop.query.order_by(Stop.id).all()]
    return render_template("index.html", bus_stops=bus_stops)

@app.route('/bus/<bus_number>')
def bus_dashboard(bus_number):
    bus = Bus.query.get(bus_number)
    if not bus:
        return render_template("bus-dashboard.html", error="Bus not found")

    user_stop = request.args.get("user_stop")
    estimated_time, remaining_time = ("Select a stop to see arrival time", "")

    if user_stop:
        estimated_time, remaining_time = calculate_arrival_time(bus, user_stop)

    route_stops = (RouteStop.query.filter_by(route_id=bus.route_id)
                   .join(Stop)
                   .order_by(RouteStop.position).all())

    stop_names = [rs.stop.name for rs in route_stops]
    current_stop_name = "Positioning..." if bus.current_stop_id is None else bus.current_stop.name

    current_index = None if bus.current_stop_id is None else next(
        (i for i, rs in enumerate(route_stops) if rs.stop_id == bus.current_stop_id), None)

    arrival_times = []
    cumulative_minutes = 0
    current_time = datetime.now()

    for i, rs in enumerate(route_stops):
        if current_index is None:
            arrival_times.append("Waiting for GPS...")
        elif i < current_index:
            arrival_times.append("Passed")
        elif i == current_index:
            arrival_times.append("Current location")
        else:
            if i > 0:
                cumulative_minutes += route_stops[i - 1].stop.time_to_next
            arrival_time = current_time + timedelta(minutes=cumulative_minutes)
            arrival_times.append(arrival_time.strftime("%I:%M %p"))

    return render_template(
        "bus-dashboard.html",
        bus={
            "id": bus.id,
            "current_stop": current_stop_name,
            "route": stop_names,
            "has_location": bus.current_stop_id is not None
        },
        user_stop=user_stop,
        estimated_time=estimated_time,
        remaining_time=remaining_time,
        arrival_times=arrival_times,
        Stop=Stop,
        current_time=current_time.strftime("%I:%M %p")
    )

@app.route('/available-buses')
def available_buses():
    start = request.args.get("start")
    end = request.args.get("end")
    bus_stops = [s.name for s in Stop.query.order_by(Stop.id).all()]

    if not start or not end:
        return render_template("available-buses.html",
                               error="Please select both start and end locations",
                               bus_stops=bus_stops)

    available_buses = []
    for bus in Bus.query.all():
        route_stops = [rs.stop.name for rs in
                       RouteStop.query.filter_by(route_id=bus.route_id)
                       .join(Stop)
                       .order_by(RouteStop.position).all()]

        if start in route_stops and end in route_stops:
            start_index = route_stops.index(start)
            end_index = route_stops.index(end)

            if start_index < end_index:
                arrival_time, remaining_time = calculate_arrival_time(bus, start)
                available_buses.append({
                    "bus": bus.id,
                    "current_stop": bus.current_stop.name if bus.current_stop else "Positioning...",
                    "arrival_time": arrival_time,
                    "remaining_time": remaining_time,
                    "destination": end
                })

    return render_template(
        "available-buses.html",
        available_buses=available_buses,
        start=start,
        end=end,
        bus_stops=bus_stops
    )

@app.context_processor
def utility_processor():
    return dict(timedelta=timedelta)

if __name__ == '__main__':
    app.run(debug=True)
