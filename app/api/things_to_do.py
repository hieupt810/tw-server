from flask import Blueprint, request

from app.schemas.things_to_do import ThingToDoSchema
from app.utils.response import APIResponse
from datetime import datetime, timezone
import uuid
from app.utils import execute_neo4j_query
import requests

bp = Blueprint('things_to_do', __name__, url_prefix='/things-to-do')


# @bp.post('')
# def create_things_to_do():
#     schema = ThingToDoSchema()
#     inputs = schema.load(request.json)
#     return APIResponse.success(data=inputs, status=201)



# in progress
# @bp.post('')
# def create_things_to_do():
#     data = request.json.copy()
#     postal_code = data.get('postal_code', '550000')

#     # Convert ratingHistogram to rating_histogram for schema
#     if 'ratingHistogram' in data:
#         histogram = data['ratingHistogram']
#         data['rating_histogram'] = [
#             {'value': [
#                 histogram.get('count1', 0),
#                 histogram.get('count2', 0),
#                 histogram.get('count3', 0),
#                 histogram.get('count4', 0),
#                 histogram.get('count5', 0),
#             ]}
#         ]
#         del data['ratingHistogram']

#     schema = ThingToDoSchema()
#     inputs = schema.load(data)

#     # Find the things_to_do category node for the city
#     result = execute_neo4j_query(
#         '''
#         MATCH (c:City {postal_code: $postal_code})-[:HAS_CATEGORY]->(cat:Category {name: "things_to_do"})
#         RETURN cat
#         ''',
#         {'postal_code': postal_code}
#     )
#     if not result:
#         return APIResponse.error('things_to_do category not found for this city', status=404)

#     category_id = result[0]['cat']['id']
#     place_id = str(uuid.uuid4())
#     created_at = datetime.now(timezone.utc).isoformat()

#     # Create the place node and link to category
#     execute_neo4j_query(
#         '''
#         MATCH (cat:Category {id: $category_id})
#         CREATE (p:ThingToDo {
#             id: $id,
#             created_at: $created_at,
#             name: $name,
#             address: $address,
#             description: $description,
#             longitude: $longitude,
#             latitude: $latitude,
#             rawRanking: $rawRanking,
#             rating: $rating,
#             web: $web,
#             phone: $phone,
#             thumbnail: $thumbnail,
#             photos: $photos,
#             rating_histogram: $rating_histogram
#         })
#         MERGE (cat)-[:HAS_PLACE]->(p)
#         ''',
#         {
#             'category_id': category_id,
#             'id': place_id,
#             'created_at': created_at,
#             'name': inputs.get('name'),
#             'address': str(inputs.get('address')),
#             'description': inputs.get('description'),
#             'longitude': inputs.get('longitude'),
#             'latitude': inputs.get('latitude'),
#             'rawRanking': inputs.get('rawRanking'),
#             'rating': inputs.get('rating'),
#             'web': inputs.get('web'),
#             'phone': inputs.get('phone'),
#             'thumbnail': inputs.get('thumbnail'),
#             'photos': inputs.get('photos'),
#             'rating_histogram': [rh['value'] for rh in inputs.get('rating_histogram', [])],
#         }
#     )

#     return APIResponse.success(data={'id': place_id, **inputs}, status=201)




@bp.post('/bulk')
def bulk_insert_things_to_do_from_api():
    # print("bulk_insert_things_to_do_from_api" )
    # print(1000)
    url = "https://api.apify.com/v2/datasets/Z2rig8cqAIhDAlJqZ/items?clean=true&fields=name,address,description,longitude,latitude,ratingHistogram,subtype,subcategories,rawRanking,phone,website,image,photos&format=json"
    response = requests.get(url)
    data = response.json()
    if not data:
        return APIResponse.error('No data from API', status=400)

    # Limit to 20 items for testing
    data = data[:20]
    print(f"Fetched {len(data)} locations from API")

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
    schema = ThingToDoSchema()

    for loc in data:
        try:
            # Process address - remove common suffixes
            address = loc.get('address', '')
            suffixes = [", Da Nang 550000 Vietnam", ", Da Nang Vietnam", "Da Nang 550000 Vietnam", "Da Nang Vietnam"]
            for suffix in suffixes:
                if address.endswith(suffix):
                    address = address[:-len(suffix)].strip()
                    break

            # Process rating histogram
            rating_histogram = loc.get('ratingHistogram') or {}
            rating_histogram_list = [
                rating_histogram.get('count1', 0),
                rating_histogram.get('count2', 0),
                rating_histogram.get('count3', 0),
                rating_histogram.get('count4', 0),
                rating_histogram.get('count5', 0),
            ]
            
            # Process photos (limit to 30)
            photos = loc.get('photos', [])
            if len(photos) > 30:
                photos = photos[:30]
            
            # Convert travelerChoiceAward to boolean
            traveler_choice = False
            if loc.get('travelerChoiceAward'):
                traveler_choice = True
                
            # Prepare data according to schema
            schema_input = {
                "name": loc.get('name', ''),
                "address": address,
                "description": loc.get('description') or "",
                "longitude": loc.get('longitude'),
                "latitude": loc.get('latitude'),
                "rawRanking": loc.get('rawRanking'),
                "web": loc.get('website') or "",
                "phone": loc.get('phone') or "",
                "thumbnail": loc.get('image') or "",
                "photos": photos,
                "rating_histogram": rating_histogram_list,
                "travelerChoiceAward": traveler_choice
            }
            
            # Validate data against schema
            place_data = schema.load(schema_input)
            place_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            
            # Create the ThingToDo node and link directly to city
            execute_neo4j_query(
                '''
                MATCH (c:City {postal_code: $postal_code})
                MERGE (p:ThingToDo {
                    name: $name,
                    longitude: $longitude,
                    latitude: $latitude
                })
                ON CREATE SET
                    p.id = $id,
                    p.created_at = $created_at,
                    p.address = $address,
                    p.description = $description,
                    p.rawRanking = $rawRanking,
                    p.web = $web,
                    p.phone = $phone,
                    p.thumbnail = $thumbnail,
                    p.photos = $photos,
                    p.rating_histogram = $rating_histogram,
                    p.travelerChoiceAward = $travelerChoiceAward
                ON MATCH SET
                    p.address = $address,
                    p.description = $description,
                    p.rawRanking = $rawRanking,
                    p.web = $web,
                    p.phone = $phone,
                    p.thumbnail = $thumbnail,
                    p.photos = $photos,
                    p.rating_histogram = $rating_histogram,
                    p.travelerChoiceAward = $travelerChoiceAward
                MERGE (c)-[:HAS_PLACE]->(p)
                RETURN p
                ''',
                {
                    'postal_code': '550000',
                    'id': place_id,
                    'created_at': created_at,
                    'name': place_data.get('name'),
                    'address': place_data.get('address'),
                    'description': place_data.get('description'),
                    'longitude': place_data.get('longitude'),
                    'latitude': place_data.get('latitude'),
                    'rawRanking': place_data.get('rawRanking'),
                    'web': place_data.get('web'),
                    'phone': place_data.get('phone'),
                    'thumbnail': place_data.get('thumbnail'),
                    'photos': place_data.get('photos'),
                    'rating_histogram': place_data.get('rating_histogram', []),
                    'travelerChoiceAward': place_data.get('travelerChoiceAward', False)
                }
            )
            
            # Create and link subtype nodes
            subtypes = loc.get('subtype', [])
            for subtype_name in subtypes:
                execute_neo4j_query(
                    '''
                    MATCH (p:ThingToDo {name: $place_name, longitude: $longitude, latitude: $latitude})
                    MERGE (s:Subtype {name: $subtype_name})
                    MERGE (p)-[:HAS_SUBTYPE]->(s)
                    ''',
                    {
                        'place_name': place_data.get('name'),
                        'longitude': place_data.get('longitude'),
                        'latitude': place_data.get('latitude'),
                        'subtype_name': subtype_name
                    }
                )
            
            # Create and link subcategory nodes
            subcategories = loc.get('subcategories', [])
            for subcategory_name in subcategories:
                execute_neo4j_query(
                    '''
                    MATCH (p:ThingToDo {name: $place_name, longitude: $longitude, latitude: $latitude})
                    MERGE (s:Subcategory {name: $subcategory_name})
                    MERGE (p)-[:HAS_SUBCATEGORY]->(s)
                    ''',
                    {
                        'place_name': place_data.get('name'),
                        'longitude': place_data.get('longitude'),
                        'latitude': place_data.get('latitude'),
                        'subcategory_name': subcategory_name
                    }
                )
            
            inserted += 1
        except Exception as e:
            errors.append(f"{loc.get('name')}: {str(e)}")

    return APIResponse.success(data={'inserted': inserted, 'errors': errors}, status=200)




@bp.get('')
def get_things_to_do():
    page = max(request.args.get('page', default=1, type=int), 1)
    per_page = min(request.args.get('per_page', default=10, type=int), 50)
    sort_order = request.args.get('order', default='desc', type=str).lower()
    sort_order = 'ASC' if sort_order == 'asc' else 'DESC'

    # Query the database for total records
    total_records_result = execute_neo4j_query(
        'MATCH (p:ThingToDo) RETURN count(p) as total_records'
    )

    # Query the database for paginated results with subtypes and subcategories
    results = execute_neo4j_query(
        f"""
        MATCH (p:ThingToDo)
        OPTIONAL MATCH (p)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (p)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        WITH p, collect(DISTINCT st.name) as subtypes, collect(DISTINCT sc.name) as subcategories
        RETURN p, subtypes, subcategories
        ORDER BY p.rawRanking {sort_order}
        SKIP $offset LIMIT $limit
        """,
        {'offset': (page - 1) * per_page, 'limit': per_page},
    )

    # Process the results
    schema = ThingToDoSchema()
    things = []
    for item in results:
        thing = schema.dump(item.get('p'))
        
        # Ensure id field is included
        if 'id' not in thing and item.get('p').get('id'):
            thing['id'] = item.get('p').get('id')
            
        # Add subtypes and subcategories
        thing['subtypes'] = item.get('subtypes', [])
        thing['subcategories'] = item.get('subcategories', [])
        
        # Calculate overall rating and round to 1 decimal place
        rh = thing.get('rating_histogram')
        if rh and isinstance(rh, list) and len(rh) == 5:
            total = sum(rh)
            if total > 0:
                overall_rating = sum((i + 1) * rh[i] for i in range(5)) / total
                overall_rating = round(overall_rating, 1)  # Round to 1 decimal place
            else:
                overall_rating = None
        else:
            overall_rating = None
        thing['overall_rating'] = overall_rating
        things.append(thing)
    
    return APIResponse.paginate(
        data=things,
        page=page,
        per_page=per_page,
        total_records=total_records_result[0]['total_records'],
    )


@bp.get('/<id>')
def get_thing_to_do_by_id(id):
    # Query the database for the specific thing to do with subtypes and subcategories
    result = execute_neo4j_query(
        """
        MATCH (p:ThingToDo {id: $id})
        OPTIONAL MATCH (p)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (p)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        WITH p, collect(DISTINCT st.name) as subtypes, collect(DISTINCT sc.name) as subcategories
        RETURN p, subtypes, subcategories
        """,
        {'id': id}
    )
    
    if not result:
        return APIResponse.error('Thing to do not found', status=404)
    
    # Process the result
    schema = ThingToDoSchema()
    item = result[0]
    thing = schema.dump(item.get('p'))
    
    # Add subtypes and subcategories
    thing['subtypes'] = item.get('subtypes', [])
    thing['subcategories'] = item.get('subcategories', [])
    
    # Calculate overall rating and round to 1 decimal place
    rh = thing.get('rating_histogram')
    if rh and isinstance(rh, list) and len(rh) == 5:
        total = sum(rh)
        if total > 0:
            overall_rating = sum((i + 1) * rh[i] for i in range(5)) / total
            overall_rating = round(overall_rating, 1)  # Round to 1 decimal place
        else:
            overall_rating = None
    else:
        overall_rating = None
    thing['overall_rating'] = overall_rating
    
    return APIResponse.success(data=thing)