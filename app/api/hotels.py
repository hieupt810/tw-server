import json
import logging

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError, fields, pre_load, validates

from app.extensions import ma
from app.models import UserFavourite, db
from app.utils import create_paging, execute_neo4j_query, get_redis, delete_place_and_related_data

logger = logging.getLogger(__name__)
blueprint = Blueprint('hotels', __name__, url_prefix='/hotels')


# Add utility function to extract price range from string
def extract_price_range(price_range_str):
    """
    Extract min_price and max_price from price_range string.
    
    Examples:
    "$1 - $25" -> (1, 25)
    "$26 - $50" -> (26, 50)
    "$101+" -> (101, None)
    """
    if not price_range_str:
        return None, None
    
    import re
    
    # Remove extra spaces and convert to lower
    price_str = price_range_str.strip()
    
    # Handle "$101+" format
    if '+' in price_str:
        match = re.search(r'\$(\d+)\+', price_str)
        if match:
            return int(match.group(1)), None
    
    # Handle "$1 - $25" format
    matches = re.findall(r'\$(\d+)', price_str)
    if len(matches) >= 2:
        return int(matches[0]), int(matches[1])
    elif len(matches) == 1:
        return int(matches[0]), int(matches[0])
    
    return None, None


# Add utility function to add min_price and max_price to hotel data
def add_price_fields_to_hotels(hotels_data):
    """Add min_price and max_price fields to hotel data based on Neo4j properties or price_range."""
    for hotel in hotels_data:
        # First check if min_price and max_price are already in the hotel data from Neo4j
        if 'min_price' not in hotel or hotel.get('min_price') is None:
            # Fallback to extracting from price_range string
            price_range = hotel.get('price_range')
            min_price, max_price = extract_price_range(price_range)
            hotel['min_price'] = min_price
            hotel['max_price'] = max_price
        # If min_price exists but max_price doesn't, ensure both are set consistently
        elif 'max_price' not in hotel or hotel.get('max_price') is None:
            # If only min_price is available, try to extract max_price from price_range
            price_range = hotel.get('price_range')
            extracted_min, extracted_max = extract_price_range(price_range)
            # Keep the existing min_price from Neo4j, but use extracted max_price if available
            hotel['max_price'] = extracted_max
    return hotels_data


class AttachCitySchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    name = fields.String(dump_only=True)

    postal_code = fields.String(required=True)

    @validates('postal_code')
    def validate_postal_code(self, value: str):
        result = execute_neo4j_query(
            """
            MATCH (c:City {postal_code: $postal_code})
            RETURN c
            """,
            {'postal_code': value},
        )
        if not result:
            raise ValidationError('City with this postal code does not exist')
        return value


class ShortHotelSchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    city = fields.Nested(AttachCitySchema, required=True)
    email = fields.Email(required=False, allow_none=True)
    image = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    name = fields.String(required=True)
    price_levels = fields.List(fields.String(), required=False, default=list)
    price_range = fields.String(required=False, allow_none=True)
    min_price = fields.Integer(dump_only=True, allow_none=True)
    max_price = fields.Integer(dump_only=True, allow_none=True)
    rating = fields.Float(required=False, allow_none=True)
    rating_histogram = fields.List(
        fields.Integer(), required=False, default=list
    )
    raw_ranking = fields.Float(required=True, load_only=True)
    street = fields.String(required=True, allow_none=True)
    type = fields.String(dump_only=True)
    is_favorite = fields.Boolean(dump_only=True, default=False)

    def on_bind_field(self, field_name, field_obj):
        super().on_bind_field(field_name, field_obj)

    @validates('rating')
    def validate_rating(self, value: float):
        if value is not None and (value < 0 or value > 5):
            raise ValidationError('Rating must be between 0 and 5')
        return value

    @validates('rating_histogram')
    def validate_rating_histogram(self, value: list):
        if value and len(value) != 5:
            raise ValidationError(
                'Rating histogram must contain exactly 5 integers'
            )
        if value and not all(isinstance(i, int) and i >= 0 for i in value):
            raise ValidationError(
                'Rating histogram must be a list of 5 non-negative integers'
            )
        return value

    @validates('raw_ranking')
    def validate_raw_ranking(self, value: float):
        if value < 0 or value > 5:
            raise ValidationError('Raw ranking must be between 0 and 5')
        return value

    @pre_load
    def calculate_rating_from_histogram(self, data, **kwargs):
        if 'rating_histogram' not in data:
            data['rating_histogram'] = [0, 0, 0, 0, 0]
            data['rating'] = 0

        # Calculate rating from histogram if available
        if (
            'rating_histogram' in data
            and isinstance(data['rating_histogram'], list)
            and len(data['rating_histogram']) == 5
        ):
            rh = data['rating_histogram']
            total = sum(rh)
            if total > 0:
                calculated_rating = (
                    sum((i + 1) * rh[i] for i in range(5)) / total
                )
                data['rating'] = round(calculated_rating, 1)
            else:
                data['rating'] = 0

        return data


class HotelSchema(ShortHotelSchema):
    # Common fields
    phone = fields.String(required=False, allow_none=True)
    photos = fields.List(fields.String(), required=False, default=list)
    website = fields.String(required=False, allow_none=True)

    # Specific fields
    ai_reviews_summary = fields.String(required=False, allow_none=True)
    description = fields.String(required=False, allow_none=True)
    features = fields.List(fields.String(), required=False, default=list)
    hotel_class = fields.String(required=False, allow_none=True)
    number_of_rooms = fields.Integer(required=False)
    price_range = fields.String(required=False, allow_none=True)
    min_price = fields.Integer(dump_only=True, allow_none=True)
    max_price = fields.Integer(dump_only=True, allow_none=True)

    @validates('number_of_rooms')
    def validate_number_of_rooms(self, value: int):
        if value is not None and value <= 0:
            raise ValidationError('Number of rooms must be a positive integer')
        return value


@blueprint.post('/')
def create_hotel():
    data = HotelSchema().load(request.get_json())
    city_postal_code = data['city']['postal_code']

    # Get data with defaults for empty lists
    features = data.get('features', [])
    price_levels = data.get('price_levels', [])

    # Base query to create hotel
    query = """
    MATCH (c:City {postal_code: $postal_code})
    CREATE
        (h:Hotel
            {
                name: $name,
                image: $image,
                latitude: $latitude,
                longitude: $longitude,
                photos: $photos,
                rating: $rating,
                rating_histogram: $rating_histogram,
                raw_ranking: $raw_ranking,
                ai_reviews_summary: $ai_reviews_summary,
                description: $description,
                email: $email,
                number_of_rooms: $number_of_rooms,
                phone: $phone,
                street: $street,
                type: 'HOTEL',
                website: $website,
                price_range: $price_range,
                created_at:
                    apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd HH:mm', 'GMT+7')
            })
    MERGE (h)-[:LOCATED_IN]->(c)
    """

    # Add features relationship if features list is not empty
    if features:
        query += """
        WITH h, c
        UNWIND $features AS feature_name
        MERGE (a:Feature {name: feature_name})
        MERGE (h)-[:HAS_FEATURE]->(a)
        """

    # Add price_levels relationship if price_levels list is not empty
    if price_levels:
        query += """
        WITH h, c
        UNWIND $price_levels AS price_level
        MERGE (pl:PriceLevel {level: price_level})
        MERGE (h)-[:HAS_PRICE_LEVEL]->(pl)
        """

    # Add hotel class relationship if hotel_class is provided
    if data.get('hotel_class'):
        query += """
        WITH h, c
        MERGE (hc:HotelClass {name: $hotel_class})
        MERGE (h)-[:BELONGS_TO_CLASS]->(hc)
        """

    # Finalize query to return data
    query += """
    RETURN
        h,
        elementId(h) AS element_id,
        c
    """

    # Execute the Neo4j query
    result = execute_neo4j_query(
        query,
        {
            'postal_code': city_postal_code,
            'name': data['name'],
            'image': data['image'],
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'photos': data.get('photos', []),
            'price_levels': price_levels,
            'rating': data.get('rating'),
            'rating_histogram': data.get('rating_histogram', []),
            'raw_ranking': data['raw_ranking'],
            'ai_reviews_summary': data.get('ai_reviews_summary'),
            'description': data.get('description'),
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'number_of_rooms': data.get('number_of_rooms'),
            'hotel_class': data.get('hotel_class'),
            'price_range': data.get('price_range'),
            'features': features,
            'street': data['street'],
        },
    )

    if not result:
        return {'error': 'Failed to create hotel.'}, 400

    # Delete cached hotel data
    redis = get_redis()
    keys_to_delete = redis.keys('hotels:*')
    if keys_to_delete:
        redis.delete(*keys_to_delete)

    hotel = result[0]['h']
    hotel['element_id'] = result[0]['element_id']
    hotel['city'] = result[0]['c']

    # Add hotel_class to the response if it was provided
    if data.get('hotel_class'):
        hotel['hotel_class'] = data['hotel_class']

    # Add price_levels to the response
    hotel['price_levels'] = price_levels

    return ShortHotelSchema().dump(hotel), 201


@blueprint.get('/')
@jwt_required(optional=True)
def get_hotels():
    # Get query parameters for pagination
    page = request.args.get('page', default=1, type=int)
    size = request.args.get('size', default=10, type=int)
    offset = (page - 1) * size

    # Get search parameter
    search = request.args.get('search', default='', type=str)
    
    # Get filter parameters - Updated to use min_price and max_price
    min_price = request.args.get('min_price', type=int)
    max_price = request.args.get('max_price', type=int)
    hotel_class = request.args.get('hotel_class', type=float)
    rating = request.args.get('rating', type=float)
    
    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Determine operation mode: search vs filter
    is_search_mode = bool(search.strip())
    is_filter_mode = any([min_price is not None, max_price is not None, hotel_class is not None, rating is not None])
    
    if is_search_mode and is_filter_mode:
        return {'error': 'Cannot use search and filter parameters simultaneously. Please use either search OR filter parameters.'}, 400
    
    if not is_search_mode and not is_filter_mode:
        # Default behavior: return all hotels
        return _get_all_hotels(page, size, offset, user_id)
    elif is_search_mode:
        return _search_hotels(search, page, size, offset, user_id)
    else:
        return _filter_hotels(min_price, max_price, hotel_class, rating, page, size, offset, user_id)


def _get_all_hotels(page, size, offset, user_id):
    """Get all hotels with pagination (default behavior)."""
    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:page={page}:size={size}:all'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            hotels = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                hotel_ids = [hotel['element_id'] for hotel in hotels['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(hotel_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for hotel in hotels['data']:
                    hotel['is_favorite'] = hotel['element_id'] in favourite_ids
            else:
                for hotel in hotels['data']:
                    hotel['is_favorite'] = False
            return hotels, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Create Cypher query parameters
    query_params = {'offset': offset, 'size': size}
    
    # Get the total count of all hotels
    count_query = """
    MATCH (h:Hotel)
    RETURN count(h) AS total_count
    """
    
    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = total_count_result[0]['total_count']

    # Get all hotels with pagination
    hotels_query = """
    MATCH (h:Hotel)
    OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
    OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
    RETURN h, elementId(h) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city
    ORDER BY h.raw_ranking DESC
    SKIP $offset
    LIMIT $size
    """
    
    result = execute_neo4j_query(hotels_query, query_params)

    # Process results - now includes price fields
    hotels_data = _process_hotel_results(result, user_id)

    # Create paginated response
    response = create_paging(
        data=ShortHotelSchema(many=True).dump(hotels_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _search_hotels(search, page, size, offset, user_id):
    """Search hotels by name."""
    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:page={page}:size={size}:search={search}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            hotels = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                hotel_ids = [hotel['element_id'] for hotel in hotels['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(hotel_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for hotel in hotels['data']:
                    hotel['is_favorite'] = hotel['element_id'] in favourite_ids
            else:
                for hotel in hotels['data']:
                    hotel['is_favorite'] = False
            return hotels, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Create Cypher query parameters
    query_params = {'offset': offset, 'size': size, 'search': search}
    
    # Get the total count of hotels matching the search criteria
    count_query = """
    MATCH (h:Hotel)
    WHERE toLower(h.name) CONTAINS toLower($search)
    RETURN count(h) AS total_count
    """
    
    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = total_count_result[0]['total_count']

    # Get the hotels with pagination and search filter
    hotels_query = """
    MATCH (h:Hotel)
    WHERE toLower(h.name) CONTAINS toLower($search)
    OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
    OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
    RETURN h, elementId(h) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city
    ORDER BY h.raw_ranking DESC
    SKIP $offset
    LIMIT $size
    """
    
    result = execute_neo4j_query(hotels_query, query_params)

    # Process results - now includes price fields
    hotels_data = _process_hotel_results(result, user_id)

    # Create paginated response
    response = create_paging(
        data=ShortHotelSchema(many=True).dump(hotels_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _filter_hotels(min_price, max_price, hotel_class, rating, page, size, offset, user_id):
    """Filter hotels based on criteria."""
    # Build cache key based on filter parameters
    cache_parts = [f'page={page}', f'size={size}', 'filter']
    if min_price is not None:
        cache_parts.append(f'min_price={min_price}')
    if max_price is not None:
        cache_parts.append(f'max_price={max_price}')
    if hotel_class is not None:
        cache_parts.append(f'hotel_class={hotel_class}')
    if rating is not None:
        cache_parts.append(f'rating={rating}')
    
    cache_key = f'hotels:{":".join(cache_parts)}'
    
    # Check if the result is cached
    redis = get_redis()
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            hotels = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                hotel_ids = [hotel['element_id'] for hotel in hotels['data']]
                favourites = (
                    db.session.query(UserFavourite.place_id)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id.in_(hotel_ids),
                    )
                    .all()
                )
                favourite_ids = set(f[0] for f in favourites)
                for hotel in hotels['data']:
                    hotel['is_favorite'] = hotel['element_id'] in favourite_ids
            else:
                for hotel in hotels['data']:
                    hotel['is_favorite'] = False
            return hotels, 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Build filter conditions and parameters
    filter_conditions = []
    query_params = {'offset': offset, 'size': size}
    
    # Price range filter - Now using direct min_price and max_price properties from Neo4j
    if min_price is not None:
        filter_conditions.append("""
        (h.min_price IS NOT NULL AND h.min_price >= $min_price) OR
        (h.min_price IS NULL AND h.max_price IS NOT NULL AND h.max_price >= $min_price)
        """)
        query_params['min_price'] = min_price
    
    if max_price is not None:
        filter_conditions.append("""
        (h.max_price IS NOT NULL AND h.max_price <= $max_price) OR
        (h.max_price IS NULL AND h.min_price IS NOT NULL AND h.min_price <= $max_price)
        """)
        query_params['max_price'] = max_price
    
    # Hotel class filter
    if hotel_class is not None:
        filter_conditions.append("toFloat(h.hotel_class) >= $hotel_class")
        query_params['hotel_class'] = hotel_class
    
    # Rating filter
    if rating is not None:
        filter_conditions.append("h.rating >= $rating")
        query_params['rating'] = rating
    
    # Build WHERE clause
    where_clause = ""
    if filter_conditions:
        where_clause = f"WHERE {' AND '.join(filter_conditions)}"
    
    # Get the total count of hotels matching the filter criteria
    count_query = f"""
    MATCH (h:Hotel)
    {where_clause}
    RETURN count(h) AS total_count
    """
    
    total_count_result = execute_neo4j_query(count_query, query_params)
    total_count = total_count_result[0]['total_count']

    # Get the hotels with pagination and filters
    hotels_query = f"""
    MATCH (h:Hotel)
    {where_clause}
    OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
    OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
    RETURN h, elementId(h) AS element_id, collect(DISTINCT pl.level) AS price_levels, c AS city
    ORDER BY h.raw_ranking DESC
    SKIP $offset
    LIMIT $size
    """
    
    result = execute_neo4j_query(hotels_query, query_params)

    # Process results
    hotels_data = _process_hotel_results(result, user_id)
    
    # Add min_price and max_price fields (fallback to extraction if not in Neo4j yet)
    hotels_data = add_price_fields_to_hotels(hotels_data)

    # Create paginated response
    response = create_paging(
        data=ShortHotelSchema(many=True).dump(hotels_data),
        page=page,
        size=size,
        offset=offset,
        total_count=total_count,
    )

    # Cache the response for 6 hours
    try:
        redis.set(cache_key, json.dumps(response), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return response, 200


def _process_hotel_results(result, user_id):
    """Process hotel query results and add element_id, price_levels, city, and price fields."""
    # Add element_id, price_levels, and city to each hotel record
    for record in result:
        record['h']['element_id'] = record['element_id']
        record['h']['price_levels'] = record['price_levels']
        record['h']['city'] = record['city']
        del record['element_id']
        del record['price_levels']
        del record['city']

    hotels_data = [record['h'] for record in result]
    
    # Add min_price and max_price fields to all hotels
    hotels_data = add_price_fields_to_hotels(hotels_data)

    # Add is_favorite field
    if user_id:
        hotel_ids = [hotel['element_id'] for hotel in hotels_data]
        favourites = (
            db.session.query(UserFavourite.place_id)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id.in_(hotel_ids),
            )
            .all()
        )
        favourite_ids = set(f[0] for f in favourites)
        for hotel in hotels_data:
            hotel['is_favorite'] = hotel['element_id'] in favourite_ids
    else:
        for hotel in hotels_data:
            hotel['is_favorite'] = False
    
    return hotels_data


@blueprint.get('/<hotel_id>/')
@jwt_required(optional=True)
def get_hotel(hotel_id):
    schema = HotelSchema()

    user_id = None
    try:
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Check if the result is cached
    redis = get_redis()
    cache_key = f'hotels:{hotel_id}'
    try:
        cached_response = redis.get(cache_key)
        if cached_response:
            hotel = json.loads(cached_response)
            # Add is_favorite field if user_id exists
            if user_id:
                favourite = (
                    db.session.query(UserFavourite)
                    .filter(
                        UserFavourite.user_id == user_id,
                        UserFavourite.place_id == hotel_id,
                    )
                    .first()
                )
                hotel['is_favorite'] = bool(favourite)
            else:
                hotel['is_favorite'] = False
            
            # Add min_price and max_price fields from price_range
            price_range = hotel.get('price_range')
            min_price, max_price = extract_price_range(price_range)
            hotel['min_price'] = min_price
            hotel['max_price'] = max_price
            
            return schema.dump(hotel), 200
    except Exception as e:
        logger.warning('Redis is not available to get data: %s', e)

    # Get the hotel details along with features, price_levels, hotel_class, and city
    result = execute_neo4j_query(
        """
        MATCH (h:Hotel)
        WHERE elementId(h) = $hotel_id
        OPTIONAL MATCH (h)-[:HAS_FEATURE]->(f:Feature)
        OPTIONAL MATCH (h)-[:HAS_PRICE_LEVEL]->(pl:PriceLevel)
        OPTIONAL MATCH (h)-[:BELONGS_TO_CLASS]->(hc:HotelClass)
        OPTIONAL MATCH (h)-[:LOCATED_IN]->(c:City)
        RETURN
            h,
            elementId(h) AS element_id,
            collect(DISTINCT f.name) AS features,
            collect(DISTINCT pl.level) AS price_levels,
            hc.name AS hotel_class,
            c AS city
        """,
        {'hotel_id': hotel_id},
    )

    if not result:
        return {'error': 'Hotel not found'}, 404

    hotel = result[0]['h']
    hotel['element_id'] = result[0]['element_id']
    hotel['features'] = result[0]['features']
    hotel['price_levels'] = result[0]['price_levels']
    hotel['hotel_class'] = result[0]['hotel_class']
    hotel['city'] = result[0]['city']

    # Add min_price and max_price fields from price_range
    price_range = hotel.get('price_range')
    min_price, max_price = extract_price_range(price_range)
    hotel['min_price'] = min_price
    hotel['max_price'] = max_price

    # Add is_favorite field
    if user_id:
        favourite = (
            db.session.query(UserFavourite)
            .filter(
                UserFavourite.user_id == user_id,
                UserFavourite.place_id == hotel_id,
            )
            .first()
        )
        hotel['is_favorite'] = bool(favourite)
    else:
        hotel['is_favorite'] = False

    # Cache the response for 6 hours (without is_favorite, since it's user-specific)
    try:
        redis.set(cache_key, json.dumps(hotel), ex=21600)
    except Exception as e:
        logger.warning('Redis is not available to set data: %s', e)

    return schema.dump(hotel), 200


@blueprint.delete('/<hotel_id>/')
def delete_hotel(hotel_id):
    """
    Delete a hotel and all related data.
    
    This endpoint will:
    - Remove the hotel from Neo4j database
    - Delete all user reviews of this hotel
    - Remove hotel from user favorites
    - Remove hotel from user trips
    - Clear all related cache entries
    """
    try:
        # First check if hotel exists and is actually a hotel
        result = execute_neo4j_query(
            """
            MATCH (h:Hotel)
            WHERE elementId(h) = $hotel_id
            RETURN h.name as name, h.type as type
            """,
            {'hotel_id': hotel_id}
        )
        
        if not result:
            return {'error': 'Hotel not found'}, 404
        
        hotel_name = result[0]['name']
        
        # Use the comprehensive deletion utility
        deletion_summary = delete_place_and_related_data(hotel_id)
        
        # Check if deletion was successful
        if not deletion_summary['place_deleted']:
            return {
                'error': 'Failed to delete hotel',
                'details': deletion_summary['errors']
            }, 500
        
        # Prepare success response
        response = {
            'message': f'Hotel "{hotel_name}" has been successfully deleted',
            'summary': {
                'hotel_deleted': deletion_summary['place_deleted'],
                'reviews_deleted': deletion_summary['reviews_deleted'],
                'favorites_removed': deletion_summary['favorites_deleted'],
                'trips_updated': deletion_summary['trips_updated'],
                'cache_cleared': deletion_summary['cache_cleared']
            }
        }
        
        # Include any non-critical errors as warnings
        if deletion_summary['errors']:
            response['warnings'] = deletion_summary['errors']
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error deleting hotel {hotel_id}: {str(e)}")
        return {
            'error': 'An unexpected error occurred while deleting the hotel',
            'details': str(e)
        }, 500
