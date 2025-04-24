import requests
import uuid
from datetime import datetime, timezone
from flask import Blueprint, abort, request
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse
from app.api.admin.cities import find_city_by_postal_code

bp = Blueprint('locations', __name__, url_prefix='/locations')

@bp.post('/')
def create_location():
    inputs = request.get_json()
    city_postal_code = inputs.get('city_postal_code')
    location = inputs.get('location')
    if not city_postal_code or not location:
        abort(400, 'city_postal_code and location are required')

    location_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    addressObj = location.get('addressObj') or {}
    address = location.get('address')
    _address = addressObj.get('street1') if addressObj.get('street1') else address
    photos = location.get('photos', [])[:10]
    ratingHistogram = location.get('ratingHistogram') or {}
    props = {
        'id': location_id,
        'created_at': created_at,
        'name': location.get('name'),
        'address': address,
        'description': location.get('description'),
        'longitude': location.get('longitude'),
        'latitude': location.get('latitude'),
        'subtype': location.get('subtype'),
        'rawRanking': location.get('rawRanking'),
        'rating': location.get('rating'),
        'numberOfReviews': location.get('numberOfReviews'),
        'phone': location.get('phone'),
        'webUrl': location.get('webUrl'),
        'website': location.get('website'),
        'image': location.get('image'),
        'photos': photos,
        '_address': _address,
        'ratingHistogram_count1': ratingHistogram.get('count1'),
        'ratingHistogram_count2': ratingHistogram.get('count2'),
        'ratingHistogram_count3': ratingHistogram.get('count3'),
        'ratingHistogram_count4': ratingHistogram.get('count4'),
        'ratingHistogram_count5': ratingHistogram.get('count5'),
        'addressObj_street1': addressObj.get('street1'),
        'addressObj_street2': addressObj.get('street2'),
        'addressObj_city': addressObj.get('city'),
        'addressObj_state': addressObj.get('state'),
        'addressObj_country': addressObj.get('country'),
        'addressObj_postalcode': addressObj.get('postalcode'),
    }

    result = execute_neo4j_query(
        '''
        MERGE (c:City {postal_code: $city_postal_code})
        MERGE (l:Location {name: $props.name, longitude: $props.longitude, latitude: $props.latitude})
        ON CREATE SET l += $props
        ON MATCH SET l += $props
        MERGE (c)-[:HAS_LOCATION]->(l)
        RETURN l
        ''',
        {'city_postal_code': city_postal_code, 'props': props}
    )
    if not result:
        abort(500, 'Something went wrong')
    return APIResponse.success(payload=props, status=201)
# NOTE: This route will only create a new Location node if there is no existing node with the same name, longitude, and latitude. Otherwise, it will update the existing node's properties and ensure the relationship to the city exists.

    # testdata 
# {
#   "city_postal_code": "550000",
#   "location": {
#     "name": "5334 Spa - Massage",
#     "address": "5332 Ho Xuan Huong Ngu Hanh Son District, Da Nang 550000 Vietnam",
#     "description": "After stressful and tired working days, we welcome you to 51 Spa – Message to relax and refresh.",
#     "longitude": 108.24441,
#     "latitude": 16.039043,
#     "subtype": ["Thermal Spas"],
#     "rawRanking": 3.3476,
#     "rating": 4.5,
#     "numberOfReviews": 140,
#     "phone": "+84 93 245 87 89",
#     "webUrl": "https://www.tripadvisor.com/Attraction_Review-g298085-d8630035-Reviews-51_Spa_Massage-Da_Nang.html",
#     "website": null,
#     "image": "https://media-cdn.tripadvisor.com/media/photo-o/11/f0/de/56/photo0jpg.jpg",
#     "photos": [
#       "https://media-cdn.tripadvisor.com/media/photo-o/09/2c/50/df/51-spa-massage.jpg",
#       "https://media-cdn.tripadvisor.com/media/daodao/photo-o/17/7a/81/bf/caption.jpg"
#     ],
#     "addressObj": {
#       "street1": "51 Ho Xuan Huong",
#       "street2": "Ngu Hanh Son District",
#       "city": "Da Nang",
#       "state": null,
#       "country": "Vietnam",
#       "postalcode": "550000"
#     },
#     "ratingHistogram": {
#       "count1": 4,
#       "count2": 10,
#       "count3": 4,
#       "count4": 13,
#       "count5": 109
#     }
#   }
# }





def test_create_location():
    url = "https://api.apify.com/v2/datasets/Z2rig8cqAIhDAlJqZ/items?clean=true&fields=name,address,addressObj,description,longitude,latitude,ratingHistogram,subtype,rawRanking,rating,numberOfReviews,phone,webUrl,website,image,photos&format=json"
    response = requests.get(url)
    data = response.json()
    if not data:
        return {'success': False, 'error': 'No data from API'}
    first_destination = data[0]
    addressObj = first_destination.get('addressObj') or {}
    address = first_destination.get('address')
    _address = addressObj.get('street1') if addressObj.get('street1') else address
    photos = first_destination.get('photos', [])[:10]
    ratingHistogram = first_destination.get('ratingHistogram') or {}
    props = {
        'id': str(uuid.uuid4()),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'name': first_destination.get('name'),
        'address': address,
        'description': first_destination.get('description'),
        'longitude': first_destination.get('longitude'),
        'latitude': first_destination.get('latitude'),
        'subtype': first_destination.get('subtype'),
        'rawRanking': first_destination.get('rawRanking'),
        'rating': first_destination.get('rating'),
        'numberOfReviews': first_destination.get('numberOfReviews'),
        'phone': first_destination.get('phone'),
        'webUrl': first_destination.get('webUrl'),
        'website': first_destination.get('website'),
        'image': first_destination.get('image'),
        'photos': photos,
        '_address': _address,
        'ratingHistogram_count1': ratingHistogram.get('count1'),
        'ratingHistogram_count2': ratingHistogram.get('count2'),
        'ratingHistogram_count3': ratingHistogram.get('count3'),
        'ratingHistogram_count4': ratingHistogram.get('count4'),
        'ratingHistogram_count5': ratingHistogram.get('count5'),
        'addressObj_street1': addressObj.get('street1'),
        'addressObj_street2': addressObj.get('street2'),
        'addressObj_city': addressObj.get('city'),
        'addressObj_state': addressObj.get('state'),
        'addressObj_country': addressObj.get('country'),
        'addressObj_postalcode': addressObj.get('postalcode'),
    }
    result = execute_neo4j_query(
        '''
        MERGE (c:City {postal_code: $city_postal_code})
        CREATE (l:Location $props)
        CREATE (c)-[:HAS_LOCATION]->(l)
        RETURN l
        ''',
        {'city_postal_code': '550000', 'props': props}
    )
    if not result:
        return {'success': False, 'error': 'Something went wrong'}
    return {'success': True, 'location': props}


def get_locations_by_city(city_postal_code, limit=20, offset=0, order='desc'):
    """
    Lấy danh sách các location thuộc city (theo postal_code), sắp xếp theo rawRanking tăng dần hoặc giảm dần.
    order: 'asc' hoặc 'desc' (default: 'desc')
    """
    order = order.lower()
    order_clause = 'ASC' if order == 'asc' else 'DESC'
    query = f'''
    MATCH (c:City {{postal_code: $city_postal_code}})-[:HAS_LOCATION]->(l:Location)
    RETURN l
    ORDER BY l.rawRanking {order_clause}
    SKIP $offset
    LIMIT $limit
    '''
    results = execute_neo4j_query(query, {
        'city_postal_code': city_postal_code,
        'limit': limit,
        'offset': offset
    })
    return [record['l'] for record in results]

@bp.get('/by-city/<city_postal_code>')
def get_locations_by_city_route(city_postal_code):
    limit = request.args.get('limit', default=20, type=int)
    offset = request.args.get('offset', default=0, type=int)
    order = request.args.get('order', default='desc', type=str)
    locations = get_locations_by_city(city_postal_code, limit=limit, offset=offset, order=order)
    return APIResponse.success(payload={'data': locations, 'pagination': {'limit': limit, 'offset': offset, 'order': order}})


@bp.delete('/city/<city_postal_code>')
def delete_all_locations_in_city(city_postal_code):
    """
    Xóa tất cả các location thuộc một thành phố (theo postal_code).
    """
    query = '''
    MATCH (c:City {postal_code: $city_postal_code})-[:HAS_LOCATION]->(l:Location)
    DETACH DELETE l
    '''
    execute_neo4j_query(query, {'city_postal_code': city_postal_code})
    return APIResponse.success(payload={'message': f'All locations in city {city_postal_code} have been deleted.'})


@bp.delete('/<location_id>')
def delete_location_by_id(location_id):
    """
    Xóa một location theo id. Khi xóa location, mối quan hệ giữa location và city cũng sẽ bị xóa tự động nhờ DETACH DELETE.
    """
    # print(f"Deleting location with ID: {location_id}")
    check_query = "MATCH (l:Location {id: $location_id}) RETURN l"
    found = execute_neo4j_query(check_query, {'location_id': location_id})
    if not found:
        return APIResponse.error(f'Location {location_id} not found.', status=404)
    query = '''
    MATCH (l:Location {id: $location_id})
    DETACH DELETE l
    '''
    execute_neo4j_query(query, {'location_id': location_id})
    return APIResponse.success(payload={'message': f'Location {location_id} has been deleted.'})


@bp.patch('/<location_id>')
def update_location(location_id):
    """
    Update a location's info and/or change its parent city.
    JSON body can include:
      - city_postal_code: to change parent city
      - location: dict of fields to update in the node
    Only update if BOTH: location exists AND new city exists (if changing city). Otherwise, return 400.
    """
    data = request.get_json()
    new_city_postal_code = data.get('city_postal_code')
    location_updates = data.get('location', {})

    # Check if location exists
    check_location = execute_neo4j_query(
        "MATCH (l:Location {id: $location_id}) RETURN l",
        {'location_id': location_id}
    )
    if not check_location:
        return APIResponse.error('Location does not exist.', status=400)

    # If changing city, check if new city exists
    if new_city_postal_code:
        city = find_city_by_postal_code(new_city_postal_code)
        if not city:
            return APIResponse.error('New city does not exist.', status=400)

    # If neither location_updates nor new_city_postal_code, do nothing
    if not location_updates and not new_city_postal_code:
        return APIResponse.error('No update data provided.', status=400)

    # 1. Update location properties if provided
    if location_updates:
        set_clause = ', '.join([f"l.{k} = ${k}" for k in location_updates.keys()])
        params = {**location_updates, 'location_id': location_id}
        execute_neo4j_query(
            f"""
            MATCH (l:Location {{id: $location_id}})
            SET {set_clause}
            """,
            params
        )

    # 2. Change parent city if needed
    if new_city_postal_code:
        execute_neo4j_query(
            """
            MATCH (old_city:City)-[r:HAS_LOCATION]->(l:Location {id: $location_id})
            DELETE r
            WITH l
            MATCH (new_city:City {postal_code: $new_city_postal_code})
            MERGE (new_city)-[:HAS_LOCATION]->(l)
            """,
            {'location_id': location_id, 'new_city_postal_code': new_city_postal_code}
        )

    return APIResponse.success(payload={'message': 'Location updated.'})


@bp.get('/<location_id>')
def get_location_by_id(location_id):
    """
    Lấy toàn bộ thông tin của một location theo id.
    """
    query = "MATCH (l:Location {id: $location_id}) RETURN l"
    result = execute_neo4j_query(query, {'location_id': location_id})
    if not result:
        return APIResponse.error('Location not found.', status=404)
    return APIResponse.success(payload=result[0]['l'])


def bulk_insert_locations_from_api():
    """
    Fetch all locations from the API and insert them into Neo4j under city postal_code '550000'.
    Returns a summary dict.
    """
    url = "https://api.apify.com/v2/datasets/Z2rig8cqAIhDAlJqZ/items?clean=true&fields=name,address,addressObj,description,longitude,latitude,ratingHistogram,subtype,rawRanking,rating,numberOfReviews,phone,webUrl,website,image,photos&format=json"
    response = requests.get(url)
    data = response.json()
    if not data:
        return {'success': False, 'error': 'No data from API'}
    inserted = 0
    errors = []
    for loc in data:
        try:
            addressObj = loc.get('addressObj') or {}
            address = loc.get('address')
            _address = addressObj.get('street1') if addressObj.get('street1') else address
            photos = loc.get('photos', [])[:10]
            ratingHistogram = loc.get('ratingHistogram') or {}
            props = {
                'id': str(uuid.uuid4()),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'name': loc.get('name'),
                'address': address,
                'description': loc.get('description'),
                'longitude': loc.get('longitude'),
                'latitude': loc.get('latitude'),
                'subtype': loc.get('subtype'),
                'rawRanking': loc.get('rawRanking'),
                'rating': loc.get('rating'),
                'numberOfReviews': loc.get('numberOfReviews'),
                'phone': loc.get('phone'),
                'webUrl': loc.get('webUrl'),
                'website': loc.get('website'),
                'image': loc.get('image'),
                'photos': photos,
                '_address': _address,
                'ratingHistogram_count1': ratingHistogram.get('count1'),
                'ratingHistogram_count2': ratingHistogram.get('count2'),
                'ratingHistogram_count3': ratingHistogram.get('count3'),
                'ratingHistogram_count4': ratingHistogram.get('count4'),
                'ratingHistogram_count5': ratingHistogram.get('count5'),
                'addressObj_street1': addressObj.get('street1'),
                'addressObj_street2': addressObj.get('street2'),
                'addressObj_city': addressObj.get('city'),
                'addressObj_state': addressObj.get('state'),
                'addressObj_country': addressObj.get('country'),
                'addressObj_postalcode': addressObj.get('postalcode'),
            }
            result = execute_neo4j_query(
                '''
                MERGE (c:City {postal_code: $city_postal_code})
                MERGE (l:Location {name: $props.name, longitude: $props.longitude, latitude: $props.latitude})
                ON CREATE SET l += $props
                ON MATCH SET l += $props
                MERGE (c)-[:HAS_LOCATION]->(l)
                RETURN l
                ''',
                {'city_postal_code': '550000', 'props': props}
            )
            if result:
                inserted += 1
            else:
                errors.append(loc.get('name'))
        except Exception as e:
            errors.append(f"{loc.get('name')}: {e}")
    return {'success': True, 'inserted': inserted, 'errors': errors}