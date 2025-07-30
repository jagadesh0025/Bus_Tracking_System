from app import app, db, Stop, Bus, Route, RouteStop, BusGPS

def populate_data():
    with app.app_context():
        # Clear existing data
        db.drop_all()
        db.create_all()

        # Create all stops
        stops = [
            Stop(name="GCE Thanjavur", time_to_next=6, latitude=10.69478, longitude=78.97539),
            Stop(name="Police Station", time_to_next=2, latitude=10.70931, longitude=78.95821),
            Stop(name="Sengipatti Turning", time_to_next=4, latitude=10.71087, longitude=78.95691),
            Stop(name="Sengipatti", time_to_next=5, latitude=10.71689, longitude=78.95457),
            Stop(name="Thirumalai Samudhram", time_to_next=4, latitude=10.72995, longitude=79.00360),
            Stop(name="Sastra", time_to_next=8, latitude=10.73076, longitude=79.01668),
            Stop(name="Prist", time_to_next=1, latitude=10.72446, longitude=79.04482),
            Stop(name="Adaikala Madha College", time_to_next=3, latitude=10.72260, longitude=79.05003),
            Stop(name="Vallam Kadai Theru", time_to_next=3, latitude=10.71986, longitude=79.05821),
            Stop(name="Vallam", time_to_next=2, latitude=10.71825, longitude=79.06242),
            Stop(name="Periyar Polytechnic", time_to_next=5, latitude=10.72023, longitude=79.06645),
            Stop(name="Collector Office", time_to_next=4, latitude=10.73206, longitude=79.09297),
            Stop(name="Vasthasavadi", time_to_next=5, latitude=10.73638, longitude=79.10474),
            Stop(name="New Bus Stand", time_to_next=0, latitude=10.75083, longitude=79.11231),
        ]
        db.session.add_all(stops)
        db.session.flush()

        # Create route
        main_route = Route(name="Main City Route")
        db.session.add(main_route)
        db.session.flush()

        # Add stops to route in order
        stop_order = [
            "GCE Thanjavur", "Police Station", "Sengipatti Turning",
            "Sengipatti", "Thirumalai Samudhram", "Sastra", "Prist",
            "Adaikala Madha College", "Vallam Kadai Theru", "Vallam", "Periyar Polytechnic",
            "Collector Office", "Vasthasavadi", "New Bus Stand"
        ]

        for position, stop_name in enumerate(stop_order, 1):
            stop = Stop.query.filter_by(name=stop_name).first()
            db.session.add(RouteStop(
                route_id=main_route.id,
                stop_id=stop.id,
                position=position
            ))

        # Create only one bus (101) with no initial stop
        bus = Bus(id="101", current_stop_id=None, route_id=main_route.id)
        db.session.add(bus)

        # Initialize empty GPS entry for bus 101
        db.session.add(BusGPS(
            bus_id="101",
            latitude=0,
            longitude=0,
            speed=0
        ))

        db.session.commit()
        print("Database successfully populated with single bus (101)!")

if __name__ == '__main__':
    populate_data()