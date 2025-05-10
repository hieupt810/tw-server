from flask import Blueprint, request
from app.schemas.restaurants import RestaurantSchema
from app.utils.response import APIResponse
from app.utils import execute_neo4j_query
import requests
import uuid
from datetime import datetime, timezone
import json

bp = Blueprint('restaurants', __name__, url_prefix='/restaurants')

@bp.post('')
def create_restaurant():
    schema = RestaurantSchema()
    inputs = schema.load(request.json)
    return APIResponse.success(data=inputs, status=201)

@bp.post('/bulk')
def bulk_insert_restaurants():
    """
    Fetch restaurants from a resource and insert them into Neo4j under city postal_code '550000',
    directly linking them to the city node. Also creates relationship nodes for cuisines, meal types, etc.
    Returns a summary dict.
    """
    print("Starting bulk_insert_restaurants")
    url = "https://api.apify.com/v2/datasets/hgtjsHgPrFjllcChK/items?clean=true&fields=name,description,phone,,address,latitude,longitude,mealTypes,cuisines,dishes,features,dietaryRestrictions,hours,ratingHistogram,website,email,rawRanking,,menuWebUrl,priceLevel,image,photos&format=json"
    response = requests.get(url)
    data = response.json()
    if not data:
        return APIResponse.error('No data from API', status=400)
    
    # Limit to 20 items for testing
    data = data[:20]
    print(f"Fetched {len(data)} restaurants from API")
    
    # Find city node with postal code 550000
    city_result = execute_neo4j_query(
        '''
        MATCH (c:City {postal_code: $postal_code})
        RETURN c
        ''',
        {'postal_code': '550000'}
    )
    if not city_result:
        return APIResponse.error('City with postal code 550000 not found', status=404)
    
    inserted = 0
    errors = []
    schema = RestaurantSchema()
    
    for loc in data:
        try:
            # Process photos (limit to 30)
            photos = loc.get('photos', [])
            if len(photos) > 30:
                photos = photos[:30]
            
            # Process hours
            simplified_hours = None
            hours_data = loc.get('hours', {})
            if hours_data:
                # Keep hours as a dictionary for schema validation
                simplified_hours = {'weekRanges': []}
                if 'weekRanges' in hours_data and isinstance(hours_data['weekRanges'], list):
                    for day_ranges in hours_data.get('weekRanges', []):
                        day_hours = []
                        if isinstance(day_ranges, list):
                            for time_range in day_ranges:
                                if isinstance(time_range, dict) and 'openHours' in time_range and 'closeHours' in time_range:
                                    day_hours.append({
                                        'openHours': time_range.get('openHours', ''),
                                        'closeHours': time_range.get('closeHours', '')
                                    })
                        simplified_hours['weekRanges'].append(day_hours)
            
            # Prepare data for schema validation
            schema_input = {
                'name': loc.get('name', ''),
                'address': loc.get('address', ''),
                'description': loc.get('description') or "",
                'longitude': loc.get('longitude'),
                'latitude': loc.get('latitude'),
                'phone': loc.get('phone') or "",
                'dishes': loc.get('dishes', []),
                'features': loc.get('features', []),
                'dietaryRestrictions': loc.get('dietaryRestrictions', []),
                'ratingHistogram': loc.get('ratingHistogram', {}),
                'website': loc.get('website') or "",
                'email': loc.get('email') or "",
                'rawRanking': loc.get('rawRanking'),
                'menuWebUrl': loc.get('menuWebUrl') or "",
                'image': loc.get('image') or "",
                'photos': photos,
                'mealTypes': loc.get('mealTypes', []),
                'cuisines': loc.get('cuisines', []),
                'priceLevel': loc.get('priceLevel') or "",
                'travelerChoiceAward': loc.get('travelerChoiceAward', False)
            }
            
            # Add hours only if properly processed
            if simplified_hours:
                schema_input['hours'] = simplified_hours
            
            # Validate with schema
            restaurant_data = schema.load(schema_input)
            restaurant_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            
            # Convert hours to JSON string for Neo4j storage
            hours_json = json.dumps(restaurant_data.get('hours', {})) if restaurant_data.get('hours') else '{}'
            
            # Create the Restaurant node and link directly to city
            execute_neo4j_query(
                '''
                MATCH (c:City {postal_code: $postal_code})
                MERGE (r:Restaurant {
                    name: $name,
                    longitude: $longitude,
                    latitude: $latitude
                })
                ON CREATE SET
                    r.id = $id,
                    r.created_at = $created_at,
                    r.address = $address,
                    r.description = $description,
                    r.phone = $phone,
                    r.dishes = $dishes,
                    r.dietaryRestrictions = $dietaryRestrictions,
                    r.website = $website,
                    r.email = $email,
                    r.rawRanking = $rawRanking,
                    r.menuWebUrl = $menuWebUrl,
                    r.image = $image,
                    r.photos = $photos,
                    r.hours = $hours,
                    r.rating_histogram = $rating_histogram,
                    r.travelerChoiceAward = $travelerChoiceAward
                ON MATCH SET
                    r.address = $address,
                    r.description = $description,
                    r.phone = $phone,
                    r.dishes = $dishes,
                    r.dietaryRestrictions = $dietaryRestrictions,
                    r.website = $website,
                    r.email = $email,
                    r.rawRanking = $rawRanking,
                    r.menuWebUrl = $menuWebUrl,
                    r.image = $image,
                    r.photos = $photos,
                    r.hours = $hours,
                    r.rating_histogram = $rating_histogram,
                    r.travelerChoiceAward = $travelerChoiceAward
                MERGE (c)-[:HAS_PLACE]->(r)
                RETURN r
                ''',
                {
                    'postal_code': '550000',
                    'id': restaurant_id,
                    'created_at': created_at,
                    'name': restaurant_data.get('name'),
                    'address': restaurant_data.get('address'),
                    'description': restaurant_data.get('description'),
                    'phone': restaurant_data.get('phone'),
                    'longitude': restaurant_data.get('longitude'),
                    'latitude': restaurant_data.get('latitude'),
                    'dishes': restaurant_data.get('dishes', []),
                    'dietaryRestrictions': restaurant_data.get('dietaryRestrictions', []),
                    'website': restaurant_data.get('website'),
                    'email': restaurant_data.get('email'),
                    'rawRanking': restaurant_data.get('rawRanking'),
                    'menuWebUrl': restaurant_data.get('menuWebUrl'),
                    'image': restaurant_data.get('image'),
                    'photos': restaurant_data.get('photos'),
                    'hours': hours_json,
                    'rating_histogram': restaurant_data.get('rating_histogram', []),
                    'travelerChoiceAward': restaurant_data.get('travelerChoiceAward', False)
                }
            )
            
            # Create and link Cuisine nodes
            if restaurant_data.get('cuisines'):
                cuisines_query = '''
                MATCH (r:Restaurant {name: $restaurant_name, longitude: $longitude, latitude: $latitude})
                UNWIND $cuisines as cuisine_name
                MERGE (c:Cuisine {name: cuisine_name})
                MERGE (r)-[:HAS_CUISINE]->(c)
                '''
                execute_neo4j_query(
                    cuisines_query,
                    {
                        'restaurant_name': restaurant_data.get('name'),
                        'longitude': restaurant_data.get('longitude'),
                        'latitude': restaurant_data.get('latitude'),
                        'cuisines': restaurant_data.get('cuisines', [])
                    }
                )
            
            # Create and link MealType nodes
            if restaurant_data.get('mealTypes'):
                meal_types_query = '''
                MATCH (r:Restaurant {name: $restaurant_name, longitude: $longitude, latitude: $latitude})
                UNWIND $meal_types as meal_type_name
                MERGE (m:MealType {name: meal_type_name})
                MERGE (r)-[:SERVES_MEAL]->(m)
                '''
                execute_neo4j_query(
                    meal_types_query,
                    {
                        'restaurant_name': restaurant_data.get('name'),
                        'longitude': restaurant_data.get('longitude'),
                        'latitude': restaurant_data.get('latitude'),
                        'meal_types': restaurant_data.get('mealTypes', [])
                    }
                )
            
            # Create and link Amenity nodes (from features)
            if restaurant_data.get('features'):
                amenities_query = '''
                MATCH (r:Restaurant {name: $restaurant_name, longitude: $longitude, latitude: $latitude})
                UNWIND $amenities as amenity_name
                MERGE (a:Amenity {name: amenity_name})
                MERGE (r)-[:HAS_AMENITY]->(a)
                '''
                execute_neo4j_query(
                    amenities_query,
                    {
                        'restaurant_name': restaurant_data.get('name'),
                        'longitude': restaurant_data.get('longitude'),
                        'latitude': restaurant_data.get('latitude'),
                        'amenities': restaurant_data.get('features', [])
                    }
                )
            
            # Handle PriceLevel nodes - split "$$ - $$$" format
            if restaurant_data.get('priceLevel'):
                price_level = restaurant_data.get('priceLevel')
                price_levels = []
                
                # Check if it has a range format like "$$ - $$$"
                if " - " in price_level:
                    parts = price_level.split(" - ")
                    # For ranges like "$$ - $$$", include all levels between
                    if len(parts) == 2:
                        start = parts[0].count("$")
                        end = parts[1].count("$")
                        for i in range(start, end + 1):
                            price_levels.append("$" * i)
                else:
                    # Single price level
                    price_levels.append(price_level)
                
                # Create and link price levels
                for level in price_levels:
                    execute_neo4j_query(
                        '''
                        MATCH (r:Restaurant {name: $restaurant_name, longitude: $longitude, latitude: $latitude})
                        MERGE (p:PriceLevel {level: $price_level})
                        MERGE (r)-[:HAS_PRICE_LEVEL]->(p)
                        ''',
                        {
                            'restaurant_name': restaurant_data.get('name'),
                            'longitude': restaurant_data.get('longitude'),
                            'latitude': restaurant_data.get('latitude'),
                            'price_level': level
                        }
                    )
            
            inserted += 1
        except Exception as e:
            errors.append(f"{loc.get('name')}: {str(e)}")
    
    return APIResponse.success(data={'inserted': inserted, 'errors': errors}, status=200)

@bp.get('')
def get_restaurants():
    page = max(request.args.get('page', default=1, type=int), 1)
    per_page = min(request.args.get('per_page', default=10, type=int), 50)
    sort_order = request.args.get('order', default='desc', type=str).lower()
    sort_order = 'ASC' if sort_order == 'asc' else 'DESC'
    
    # Get filter parameters
    cuisine = request.args.get('cuisine')
    meal_type = request.args.get('meal_type')
    price_level = request.args.get('price_level')
    amenity = request.args.get('amenity')
    min_rating = request.args.get('min_rating', type=float)
    award_winners = request.args.get('award_winners', type=bool, default=False)
    
    # Build query based on filters
    query_params = {'offset': (page - 1) * per_page, 'limit': per_page}
    match_clause = "MATCH (r:Restaurant)"
    where_clauses = []
    
    if cuisine:
        match_clause += "\nMATCH (r)-[:HAS_CUISINE]->(c:Cuisine {name: $cuisine})"
        query_params['cuisine'] = cuisine
    
    if meal_type:
        match_clause += "\nMATCH (r)-[:SERVES_MEAL]->(m:MealType {name: $meal_type})"
        query_params['meal_type'] = meal_type
    
    if price_level:
        match_clause += "\nMATCH (r)-[:HAS_PRICE_LEVEL]->(p:PriceLevel {level: $price_level})"
        query_params['price_level'] = price_level
    
    if amenity:
        match_clause += "\nMATCH (r)-[:HAS_AMENITY]->(a:Amenity {name: $amenity})"
        query_params['amenity'] = amenity
    
    if min_rating:
        where_clauses.append("r.rawRanking >= $min_rating")
        query_params['min_rating'] = min_rating
    
    if award_winners:
        where_clauses.append("r.travelerChoiceAward = true")
    
    where_clause = "\nWHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # Query the database for total records
    count_query = match_clause + where_clause + "\nRETURN count(r) as total_records"
    total_records_result = execute_neo4j_query(count_query, query_params)
    
    # Query the database for paginated results with related nodes
    results_query = f"""
    {match_clause}
    {where_clause}
    WITH r
    OPTIONAL MATCH (r)-[:HAS_CUISINE]->(c:Cuisine)
    OPTIONAL MATCH (r)-[:SERVES_MEAL]->(m:MealType)
    OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(p:PriceLevel)
    OPTIONAL MATCH (r)-[:HAS_AMENITY]->(a:Amenity)
    WITH r, collect(DISTINCT c.name) as cuisines, collect(DISTINCT m.name) as meal_types, 
         collect(DISTINCT p.level) as price_levels, collect(DISTINCT a.name) as amenities
    RETURN r, cuisines, meal_types, price_levels, amenities
    ORDER BY r.rawRanking {sort_order}
    SKIP $offset LIMIT $limit
    """
    
    results = execute_neo4j_query(results_query, query_params)
    
    # Process the results
    schema = RestaurantSchema()
    restaurants = []
    for item in results:
        # Get base restaurant data
        r_node = item.get('r')
        # Get hours directly from node properties
        hours_str = r_node.get('hours', '{}')
        
        # Create restaurant dict (without hours)
        restaurant = schema.dump(r_node)
        
        # Ensure id field is included
        if 'id' not in restaurant and r_node.get('id'):
            restaurant['id'] = r_node.get('id')
        
        # Parse hours separately
        try:
            if isinstance(hours_str, str) and hours_str:
                # Remove escape characters that might cause issues
                clean_hours_str = hours_str.replace('\\"', '"')
                hours_obj = json.loads(clean_hours_str)
                restaurant['hours'] = hours_obj
            else:
                restaurant['hours'] = {}
        except Exception as e:
            print(f"Error parsing hours for {restaurant.get('name')}: {str(e)}")
            print(f"Raw hours data: {hours_str}")
            restaurant['hours'] = {}
        
        # Add relationship data
        restaurant['cuisines'] = item.get('cuisines', [])
        restaurant['mealTypes'] = item.get('meal_types', [])
        restaurant['price_levels'] = item.get('price_levels', [])
        
        # Map amenities to features (for consistency with input data)
        restaurant['features'] = item.get('amenities', [])
        
        # Calculate overall rating and round to 1 decimal place
        rh = restaurant.get('rating_histogram')
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                overall_rating = sum((i + 1) * rh[i] for i in range(5)) / total
                overall_rating = round(overall_rating, 1)
                restaurant['overall_rating'] = overall_rating
            else:
                restaurant['overall_rating'] = None
        else:
            restaurant['overall_rating'] = None
        
        # Remove priceLevel field since we have price_levels
        if 'priceLevel' in restaurant:
            del restaurant['priceLevel']
        
        restaurants.append(restaurant)
    
    return APIResponse.paginate(
        data=restaurants,
        page=page,
        per_page=per_page,
        total_records=total_records_result[0]['total_records'],
    )

@bp.get('/debug-hours')
def debug_restaurant_hours():
    """Debug endpoint to examine hours data directly from the database"""
    restaurants = execute_neo4j_query(
        '''
        MATCH (r:Restaurant)
        RETURN r.name as name, r.hours as hours
        LIMIT 5
        '''
    )
    
    results = []
    for restaurant in restaurants:
        name = restaurant.get('name', 'Unknown')
        hours_str = restaurant.get('hours', '{}')
        
        result = {
            'name': name,
            'hours_type': type(hours_str).__name__,
            'hours_raw': hours_str
        }
        
        # Try to parse hours
        try:
            if isinstance(hours_str, str):
                parsed = json.loads(hours_str)
                result['hours_parsed'] = parsed
                result['parsing_success'] = True
            else:
                result['parsing_success'] = False
                result['error'] = 'Hours is not a string'
        except Exception as e:
            result['parsing_success'] = False
            result['error'] = str(e)
        
        results.append(result)
    
    return APIResponse.success(data=results)

@bp.get('/<id>')
def get_restaurant_by_id(id):
    # Query the database for the specific restaurant with related nodes
    result = execute_neo4j_query(
        """
        MATCH (r:Restaurant {id: $id})
        OPTIONAL MATCH (r)-[:HAS_CUISINE]->(c:Cuisine)
        OPTIONAL MATCH (r)-[:SERVES_MEAL]->(m:MealType)
        OPTIONAL MATCH (r)-[:HAS_PRICE_LEVEL]->(p:PriceLevel)
        OPTIONAL MATCH (r)-[:HAS_AMENITY]->(a:Amenity)
        WITH r, collect(DISTINCT c.name) as cuisines, collect(DISTINCT m.name) as meal_types, 
             collect(DISTINCT p.level) as price_levels, collect(DISTINCT a.name) as amenities
        RETURN r, cuisines, meal_types, price_levels, amenities
        """,
        {'id': id}
    )
    
    if not result:
        return APIResponse.error('Restaurant not found', status=404)
    
    # Process the result
    schema = RestaurantSchema()
    item = result[0]
    r_node = item.get('r')
    
    # Get hours directly from node properties
    hours_str = r_node.get('hours', '{}')
    
    # Create restaurant dict (without hours)
    restaurant = schema.dump(r_node)
    
    # Parse hours separately
    try:
        if isinstance(hours_str, str) and hours_str:
            # Remove escape characters that might cause issues
            clean_hours_str = hours_str.replace('\\"', '"')
            hours_obj = json.loads(clean_hours_str)
            restaurant['hours'] = hours_obj
        else:
            restaurant['hours'] = {}
    except Exception as e:
        print(f"Error parsing hours for {restaurant.get('name')}: {str(e)}")
        restaurant['hours'] = {}
    
    # Add relationship data
    restaurant['cuisines'] = item.get('cuisines', [])
    restaurant['mealTypes'] = item.get('meal_types', [])
    restaurant['price_levels'] = item.get('price_levels', [])
    
    # Map amenities to features (for consistency with input data)
    restaurant['features'] = item.get('amenities', [])
    
    # Calculate overall rating and round to 1 decimal place
    rh = restaurant.get('rating_histogram')
    if rh and isinstance(rh, list) and len(rh) == 5:
        total = sum(rh)
        if total > 0:
            overall_rating = sum((i + 1) * rh[i] for i in range(5)) / total
            overall_rating = round(overall_rating, 1)
            restaurant['overall_rating'] = overall_rating
        else:
            restaurant['overall_rating'] = None
    else:
        restaurant['overall_rating'] = None
    
    # Remove priceLevel field since we have price_levels
    if 'priceLevel' in restaurant:
        del restaurant['priceLevel']
    
    return APIResponse.success(data=restaurant)
