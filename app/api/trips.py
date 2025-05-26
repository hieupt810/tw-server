import logging
import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import fields
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import CamelCaseSchema
from app.models import Trip, UserTrip, db
from app.utils import execute_neo4j_query

logger = logging.getLogger(__name__)
blueprint = Blueprint('trips', __name__, url_prefix='/trips')


# Add schema classes for trip responses
class CitySchema(CamelCaseSchema):
    name = fields.String(dump_only=True)
    postal_code = fields.String(dump_only=True)


class TripPlaceSchema(CamelCaseSchema):
    city = fields.Nested(CitySchema, dump_only=True)
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    email = fields.String(dump_only=True)
    image = fields.String(dump_only=True)
    latitude = fields.Float(dump_only=True)
    longitude = fields.Float(dump_only=True)
    name = fields.String(dump_only=True)
    rating = fields.Float(dump_only=True)
    rating_histogram = fields.List(fields.Integer(), dump_only=True)
    raw_ranking = fields.Float(dump_only=True)
    street = fields.String(dump_only=True)
    type = fields.String(dump_only=True)
    order = fields.Integer(dump_only=True)


class TripDetailsSchema(CamelCaseSchema):
    id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    created_at = fields.String(dump_only=True)
    updated_at = fields.String(dump_only=True)
    is_optimized = fields.Boolean(dump_only=True)
    places = fields.List(fields.Nested(TripPlaceSchema), dump_only=True)


# ===== User Trip Endpoints =====
@blueprint.post('/')
@jwt_required()
def create_user_trip():
    """Create a new user trip."""
    user_id = get_jwt_identity()
    data = request.json

    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400

    try:
        # Create new user trip
        user_trip = UserTrip(
            user_id=user_id,
            name=data['name'].strip(),
            is_optimized=data.get('isOptimized', False),
        )

        db.session.add(user_trip)
        db.session.commit()

        return jsonify(
            {
                'id': str(user_trip.id),
                'userId': str(user_trip.user_id),
                'name': user_trip.name,
                'isOptimized': user_trip.is_optimized,
                'createdAt': user_trip.created_at.isoformat(),
                'updatedAt': user_trip.updated_at.isoformat(),
            }
        ), 201

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error creating user trip: {str(e)}')
        return jsonify({'error': 'Failed to create user trip'}), 500


@blueprint.get('/')
@jwt_required()
def get_user_trips():
    """Get all user trips for the authenticated user."""
    user_id = get_jwt_identity()
    try:
        user_trips = (
            UserTrip.query.filter_by(user_id=user_id)
            .order_by(UserTrip.created_at.desc())
            .all()
        )

        result = []
        for trip in user_trips:
            # Get all places for this trip
            places = Trip.query.filter_by(trip_id=trip.id).all()
            
            # Initialize counters
            number_hotel = 0
            number_restaurant = 0
            number_thingtodo = 0
            
            # Get place details from Neo4j in batch
            place_ids = [place.place_id for place in places]
            if place_ids:
                place_types = execute_neo4j_query(
                    """
                    MATCH (p)
                    WHERE elementId(p) IN $place_ids
                    RETURN elementId(p) AS element_id, labels(p) AS types
                    """,
                    {'place_ids': place_ids},
                )
                
                # Count place types
                for place_type in place_types:
                    types = place_type['types']
                    if 'Hotel' in types:
                        number_hotel += 1
                    elif 'Restaurant' in types:
                        number_restaurant += 1
                    elif 'ThingToDo' in types:
                        number_thingtodo += 1

            result.append(
                {
                    'id': str(trip.id),
                    'name': trip.name,
                    'createdAt': trip.created_at.isoformat(),
                    'updatedAt': trip.updated_at.isoformat(),
                    'placeCount': len(places),
                    'isOptimized': trip.is_optimized,
                    'numberHotel': number_hotel,
                    'numberRestaurant': number_restaurant,
                    'numberThingtodo': number_thingtodo,
                }
            )

        return jsonify(result), 200

    except SQLAlchemyError as e:
        logger.error(f'Error fetching user trips: {str(e)}')
        return jsonify({'error': 'Failed to fetch user trips'}), 500


@blueprint.post('/<uuid:trip_id>')
@jwt_required()
def add_place_to_trip(trip_id):
    """Add a place to a user trip."""
    user_id = get_jwt_identity()
    data = request.json

    if not data or 'place_id' not in data:
        return jsonify({'error': 'Place ID is required'}), 400

    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        # Check if place already exists in trip
        existing_place = Trip.query.filter_by(
            trip_id=trip_id, place_id=data['place_id']
        ).first()

        if existing_place:
            return jsonify({'error': 'Place already exists in this trip'}), 400

        # Get the next order number
        max_order = (
            db.session.query(db.func.max(Trip.order))
            .filter_by(trip_id=trip_id)
            .scalar()
            or 0
        )
        next_order = max_order + 1

        # Create new trip place
        trip_place = Trip(
            trip_id=trip_id, place_id=data['place_id'], order=next_order
        )

        # Set is_optimized to false since we're adding a new place
        user_trip.is_optimized = False

        db.session.add(trip_place)
        db.session.commit()

        return jsonify(
            {
                'id': str(trip_place.id),
                'tripId': str(trip_place.trip_id),
                'placeId': trip_place.place_id,
                'order': trip_place.order,
                'createdAt': trip_place.created_at.isoformat(),
                'updatedAt': trip_place.updated_at.isoformat(),
            }
        ), 201

    except SQLAlchemyError as e:
        print("Error adding place to trip: ", e)
        db.session.rollback()
        logger.error(f'Error adding place to trip: {str(e)}')
        return jsonify({'error': 'Failed to add place to trip'}), 500


@blueprint.delete('/<uuid:trip_id>')
@jwt_required()
def delete_user_trip(trip_id):
    """Delete a user trip."""
    user_id = get_jwt_identity()

    try:
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        # Delete all places in this trip first
        Trip.query.filter_by(trip_id=trip_id).delete()

        # Then delete the trip itself
        db.session.delete(user_trip)
        db.session.commit()

        return jsonify({'message': 'Trip deleted successfully'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error deleting user trip: {str(e)}')
        return jsonify({'error': 'Failed to delete user trip'}), 500


@blueprint.patch('/<uuid:trip_id>')
@jwt_required()
def update_user_trip(trip_id):
    """Update a user trip."""
    user_id = get_jwt_identity()
    data = request.json

    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400

    try:
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        user_trip.name = data['name']
        db.session.commit()

        return jsonify(
            {
                'id': str(user_trip.id),
                'name': user_trip.name,
                'created_at': user_trip.created_at.isoformat(),
                'updated_at': user_trip.updated_at.isoformat(),
            }
        ), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error updating user trip: {str(e)}')
        return jsonify({'error': 'Failed to update user trip'}), 500


@blueprint.get('/<uuid:trip_id>')
@jwt_required()
def get_trip_places(trip_id):
    """Get all places in a user trip with trip information."""
    user_id = get_jwt_identity()

    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        # Get places in trip, ordered by order field (ascending)
        places = (
            Trip.query.filter_by(trip_id=trip_id)
            .order_by(Trip.order)
            .all()
        )

        if not places:
            return jsonify({
                'trip': {
                    'id': str(user_trip.id),
                    'name': user_trip.name,
                    'isOptimized': user_trip.is_optimized,
                    'createdAt': user_trip.created_at.isoformat(),
                    'updatedAt': user_trip.updated_at.isoformat(),
                    'userId': str(user_trip.user_id),
                    'totalPlaces': 0,
                    'totalDistance': None,
                    'totalDistanceKm': None,
                    'numberHotel': 0,
                    'numberRestaurant': 0,
                    'numberThingtodo': 0,
                },
                'places': [],
            }), 200

        # Batch fetch place details from Neo4j
        place_ids = [place.place_id for place in places]
        place_details_map = {}
        
        # Execute a single Neo4j query to get all places
        results = execute_neo4j_query(
            """
            MATCH (p)
            WHERE elementId(p) IN $place_ids
            OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
            RETURN p, elementId(p) AS element_id, labels(p) AS types, c
            """,
            {'place_ids': place_ids},
        )

        # Initialize counters
        number_hotel = 0
        number_restaurant = 0
        number_thingtodo = 0

        # Process results and create a map of place_id to place details
        for result in results:
            place_data = result['p']
            place_id = result['element_id']
            place_types = result['types']
            city_data = result['c']

            # Count place types
            if 'Hotel' in place_types:
                number_hotel += 1
            elif 'Restaurant' in place_types:
                number_restaurant += 1
            elif 'ThingToDo' in place_types:
                number_thingtodo += 1

            # Add city data if available
            if city_data:
                place_data['city'] = {
                    'postal_code': city_data.get('postal_code', ''),
                    'name': city_data.get('name', ''),
                }

            # Determine place type and standardize it
            place_type = None
            standardized_type = 'UNKNOWN'
            for type_label in place_types:
                if type_label == 'Hotel':
                    place_type = type_label
                    standardized_type = 'HOTEL'
                    break
                elif type_label == 'Restaurant':
                    place_type = type_label
                    standardized_type = 'RESTAURANT'
                    break
                elif type_label == 'ThingToDo':
                    place_type = type_label
                    standardized_type = 'THING-TO-DO'
                    break

            if not place_type:
                place_type = place_data.get('type', 'Unknown')

            place_data['type'] = standardized_type
            place_data['element_id'] = place_id

            # Set default values for missing fields
            if 'rating_histogram' not in place_data or not place_data['rating_histogram']:
                place_data['rating_histogram'] = [0, 0, 0, 0, 0]

            if 'rating' not in place_data or place_data['rating'] is None:
                rh = place_data.get('rating_histogram', [])
                if rh and isinstance(rh, list) and len(rh) == 5:
                    total = sum(rh)
                    if total > 0:
                        rating = sum((i + 1) * rh[i] for i in range(5)) / total
                        place_data['rating'] = round(rating, 1)
                    else:
                        place_data['rating'] = 0
                else:
                    place_data['rating'] = 0

            # Convert camelCase keys to snake_case
            camel_to_snake_mappings = {
                'ratingHistogram': 'rating_histogram',
                'rawRanking': 'raw_ranking',
                'elementId': 'element_id',
                'createdAt': 'created_at',
                'updatedAt': 'updated_at',
            }

            for camel, snake in camel_to_snake_mappings.items():
                if camel in place_data and snake not in place_data:
                    place_data[snake] = place_data[camel]

            # Filter fields to only include those from short schemas
            common_fields = [
                'element_id',
                'city',
                'email',
                'image',
                'latitude',
                'longitude',
                'name',
                'rating',
                'rating_histogram',
                'raw_ranking',
                'street',
                'type',
            ]

            filtered_data = {
                k: place_data.get(k) for k in common_fields if k in place_data
            }
            place_details_map[place_id] = filtered_data

        # Combine place details with trip place data
        place_details = []
        for place in places:
            place_info = place_details_map.get(place.place_id)
            if place_info:
                place_info['order'] = place.order
                place_info['createdAt'] = place.created_at.isoformat()
                place_details.append(place_info)

        # Calculate total distance only if trip is optimized and has enough places
        total_distance = None
        total_distance_km = None
        if user_trip.is_optimized and len(place_details) >= 2:
            distance_matrix = calculate_distance_matrix(place_details)
            total_distance = calculate_total_distance(
                range(len(place_details)), distance_matrix
            )
            total_distance_km = round(total_distance / 1000, 2)

        result = {
            'trip': {
                'id': str(user_trip.id),
                'name': user_trip.name,
                'isOptimized': user_trip.is_optimized,
                'createdAt': user_trip.created_at.isoformat(),
                'updatedAt': user_trip.updated_at.isoformat(),
                'userId': str(user_trip.user_id),
                'totalPlaces': len(place_details),
                'totalDistance': total_distance,
                'totalDistanceKm': total_distance_km,
                'numberHotel': number_hotel,
                'numberRestaurant': number_restaurant,
                'numberThingtodo': number_thingtodo,
            },
            'places': TripPlaceSchema(many=True).dump(place_details),
        }

        return jsonify(result), 200

    except SQLAlchemyError as e:
        logger.error(f'Error fetching trip places: {str(e)}')
        return jsonify({'error': 'Failed to fetch trip places'}), 500


@blueprint.delete('/<uuid:trip_id>/places/<string:place_id>')
@jwt_required()
def delete_trip_place(trip_id, place_id):
    """Delete a place from a trip."""
    user_id = get_jwt_identity()

    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        # Get the place
        place = Trip.query.filter_by(trip_id=trip_id, place_id=place_id).first()

        if not place:
            return jsonify({'error': 'Place not found in trip'}), 404

        # Delete the place
        db.session.delete(place)

        # Set is_optimized to false since we're removing a place
        user_trip.is_optimized = False

        # Reorder remaining places to keep order consistent
        remaining_places = (
            Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        )
        for i, rp in enumerate(remaining_places, 1):
            rp.order = i

        db.session.commit()

        return jsonify({'message': 'Place removed from trip successfully'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error deleting trip place: {str(e)}')
        return jsonify({'error': 'Failed to delete trip place'}), 500


@blueprint.post('/<uuid:trip_id>/places/reorder')
@jwt_required()
def reorder_trip_places(trip_id):
    """Reorder places in a trip."""
    user_id = get_jwt_identity()
    data = request.json

    if not data or 'places' not in data or not isinstance(data['places'], list):
        return jsonify({'error': 'Places array is required'}), 400

    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        # Set is_optimized to false since we're reordering places
        user_trip.is_optimized = False

        # Create a mapping of place_id to new order
        place_order_map = {
            place: i + 1 for i, place in enumerate(data['places'])
        }

        # Update orders
        for place_id, new_order in place_order_map.items():
            place = Trip.query.filter_by(
                trip_id=trip_id, place_id=place_id
            ).first()
            if place:
                place.order = new_order

        db.session.commit()

        # Get updated places
        updated_places = (
            Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        )

        # Return TripPlaceSchema response with place details from Neo4j
        result = []
        for place in updated_places:
            place_info = get_place_details_from_neo4j(place.place_id)
            if place_info:
                place_info['order'] = place.order
                place_info['created_at'] = place.created_at.isoformat()
                result.append(place_info)

        return jsonify(TripPlaceSchema(many=True).dump(result)), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error reordering trip places: {str(e)}')
        return jsonify({'error': 'Failed to reorder trip places'}), 500


def get_place_details_from_neo4j(place_id):
    """Get place details from Neo4j regardless of place type."""
    # First, try to find the place by elementId
    result = execute_neo4j_query(
        """
        MATCH (p)
        WHERE elementId(p) = $place_id
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        RETURN p, elementId(p) AS element_id, labels(p) AS types, c
        """,
        {'place_id': place_id},
    )

    if not result:
        return None

    # Extract the place data and determine its type
    place_data = result[0]['p']
    place_data['element_id'] = result[0]['element_id']
    place_types = result[0]['types']
    city_data = result[0]['c']

    # Add city data if available (without created_at)
    if city_data:
        place_data['city'] = {
            'postal_code': city_data.get('postal_code', ''),
            'name': city_data.get('name', ''),
        }

    # Determine place type and standardize it
    place_type = None
    standardized_type = 'UNKNOWN'
    for type_label in place_types:
        if type_label == 'Hotel':
            place_type = type_label
            standardized_type = 'HOTEL'
            break
        elif type_label == 'Restaurant':
            place_type = type_label
            standardized_type = 'RESTAURANT'
            break
        elif type_label == 'ThingToDo':
            place_type = type_label
            standardized_type = 'THING-TO-DO'
            break

    if not place_type:
        # Default to the 'type' field if available
        place_type = place_data.get('type', 'Unknown')

    # Ensure 'type' field is standardized
    place_data['type'] = standardized_type

    # No need to fetch price_levels as we're not including them in the response

    # Ensure all fields match the expected format in ShortSchemas
    # Provide default values for any missing fields
    if (
        'rating_histogram' not in place_data
        or not place_data['rating_histogram']
    ):
        place_data['rating_histogram'] = [0, 0, 0, 0, 0]

    if 'rating' not in place_data or place_data['rating'] is None:
        # Calculate rating from histogram if available
        rh = place_data.get('rating_histogram', [])
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                rating = sum((i + 1) * rh[i] for i in range(5)) / total
                place_data['rating'] = round(rating, 1)
            else:
                place_data['rating'] = 0
        else:
            place_data['rating'] = 0

    # Convert camelCase keys to snake_case if needed
    camel_to_snake_mappings = {
        'ratingHistogram': 'rating_histogram',
        'rawRanking': 'raw_ranking',
        'elementId': 'element_id',
        'createdAt': 'created_at',
        'updatedAt': 'updated_at',
    }

    for camel, snake in camel_to_snake_mappings.items():
        if camel in place_data and snake not in place_data:
            place_data[snake] = place_data[camel]

    # Filter fields to only include those from short schemas (excluding created_at which will be set from Trip)
    common_fields = [
        'element_id',
        'city',
        'email',
        'image',
        'latitude',
        'longitude',
        'name',
        'rating',
        'rating_histogram',
        'raw_ranking',
        'street',
        'type',
    ]

    # Create filtered dict with only fields from short schemas
    filtered_data = {
        k: place_data.get(k) for k in common_fields if k in place_data
    }

    return filtered_data


@blueprint.delete('/all')
@jwt_required()
def delete_all_user_trips():
    """Delete all trips for the authenticated user."""
    user_id = get_jwt_identity()

    try:
        # Get all trips for the user
        user_trips = UserTrip.query.filter_by(user_id=user_id).all()

        if not user_trips:
            return jsonify({'message': 'No trips found'}), 200

        # Delete all places in these trips first
        for trip in user_trips:
            Trip.query.filter_by(trip_id=trip.id).delete()

        # Then delete all trips
        for trip in user_trips:
            db.session.delete(trip)

        db.session.commit()

        return jsonify(
            {
                'message': 'All trips deleted successfully',
                'deletedCount': len(user_trips),
            }
        ), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f'Error deleting all user trips: {str(e)}')
        return jsonify({'error': 'Failed to delete trips'}), 500


def calculate_distance_matrix(places):
    """Calculate distance matrix between all places."""
    size = len(places)
    matrix = [[0] * size for _ in range(size)]

    for i in range(size):
        for j in range(size):
            if i != j:
                # Calculate Haversine distance between two points
                lat1, lon1 = places[i]['latitude'], places[i]['longitude']
                lat2, lon2 = places[j]['latitude'], places[j]['longitude']

                # Convert to radians
                lat1, lon1, lat2, lon2 = map(
                    math.radians, [lat1, lon1, lat2, lon2]
                )

                # Haversine formula
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = (
                    math.sin(dlat / 2) ** 2
                    + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                )
                c = 2 * math.asin(math.sqrt(a))
                r = 6371  # Radius of earth in kilometers

                matrix[i][j] = int(
                    c * r * 1000
                )  # Convert to meters and round to integer

    return matrix


def solve_tsp(distance_matrix):
    """Solve TSP using Google OR-Tools."""
    manager = pywrapcp.RoutingIndexManager(len(distance_matrix), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Set first solution heuristic
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    # Solve the problem
    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        return None

    # Get the route
    index = routing.Start(0)
    route = []
    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)
        route.append(node_index)
        index = solution.Value(routing.NextVar(index))

    # Add the last node
    node_index = manager.IndexToNode(index)
    route.append(node_index)

    # print(f"TSP route before processing: {route}")

    # Remove the duplicate starting point if it exists
    if len(route) > 1 and route[0] == route[-1]:
        route = route[:-1]

    # print(f"TSP route after removing duplicate: {route}")

    return route


def calculate_total_distance(route, distance_matrix):
    """Calculate total distance of the route."""
    total_distance = 0
    for i in range(len(route) - 1):
        total_distance += distance_matrix[route[i]][route[i + 1]]
    return total_distance


@blueprint.post('/<uuid:trip_id>/optimize')
@jwt_required()
def optimize_trip(trip_id):
    """Optimize trip route using TSP."""
    user_id = get_jwt_identity()

    try:
        # Verify trip exists and belongs to user
        user_trip = UserTrip.query.filter_by(
            id=trip_id, user_id=user_id
        ).first()

        if not user_trip:
            return jsonify({'error': 'Trip not found'}), 404

        # Get all places in trip
        places = (
            Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        )

        if len(places) < 2:
            return jsonify(
                {'error': 'Trip must have at least 2 places to optimize'}
            ), 400

        # Get place details from Neo4j
        place_details = []
        for place in places:
            place_info = get_place_details_from_neo4j(place.place_id)
            if place_info:
                place_info['trip_place_id'] = str(
                    place.id
                )  # Keep track of the trip place ID
                place_details.append(place_info)

        if not place_details:
            return jsonify({'error': 'No valid places found in trip'}), 400

        # Calculate distance matrix
        distance_matrix = calculate_distance_matrix(place_details)

        # Solve TSP
        optimized_route = solve_tsp(distance_matrix)

        if not optimized_route:
            return jsonify({'error': 'Failed to optimize route'}), 500

        # Calculate total distance
        total_distance = calculate_total_distance(
            optimized_route, distance_matrix
        )

        # print(f"Optimized route: {optimized_route}")

        # First, reset all orders to 0
        for place in places:
            place.order = 0
            # print(f"Reset place {place.id} order to 0")

        # Update trip places order
        for i, place_index in enumerate(optimized_route):
            place = Trip.query.get(place_details[place_index]['trip_place_id'])
            if place:
                place.order = i + 1  # Start from 1
                # print(f"Set place {place.id} order to {i + 1}")

        # Update trip optimization status
        user_trip.is_optimized = True

        db.session.commit()

        # Get updated places in optimized order
        updated_places = (
            Trip.query.filter_by(trip_id=trip_id).order_by(Trip.order).all()
        )
        optimized_places = []

        for place in updated_places:
            place_info = get_place_details_from_neo4j(place.place_id)
            if place_info:
                place_info['order'] = place.order
                # print(f"Final place {place.id} order: {place.order}")
                optimized_places.append(place_info)

        # Sort places by order to ensure correct sequence
        optimized_places.sort(key=lambda x: x['order'])

        # Print final orders for verification
        # print("Final orders:")
        # for place in optimized_places:
        #     print(f"Place: {place['name']}, Order: {place['order']}")

        return jsonify(
            {
                'message': 'Trip optimized successfully',
                'isOptimized': True,
                'totalDistance': total_distance,  # in meters
                'totalDistanceKm': round(
                    total_distance / 1000, 2
                ),  # in kilometers
                'places': TripPlaceSchema(many=True).dump(optimized_places),
            }
        ), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        print(f'Error optimizing trip: {str(e)}')
        return jsonify({'error': 'Failed to optimize trip'}), 500
