import uuid
from datetime import datetime, timezone
 
from flask import Blueprint, abort, request
 
from app.constants import MAX_PAGINATION_LIMIT
from app.schemas.cities import CitySchema
from app.utils import execute_neo4j_query
from app.utils.response import APIResponse
 
bp = Blueprint('cities', __name__, url_prefix='/cities')
 
 
@bp.post('/')
def create_city():
    schema = CitySchema()
    inputs = schema.load(request.get_json())
 
    # Query the database
    result = execute_neo4j_query(
        """
        MERGE (c:City {postal_code: $postal_code})
        SET c.id = $id, c.created_at = $created_at, c.name = $name
        RETURN c
        """,
        {
            'id': str(uuid.uuid4()),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'name': inputs['name'],
            'postal_code': inputs['postal_code'],
        },
    )
    if not result:
        abort(500, 'Something went wrong')
 
    return APIResponse.success(payload=schema.dump(result['c']), status=201)
 
 
@bp.get('/')
def get_cities():
    limit = min(
        request.args.get('limit', default=10, type=int), MAX_PAGINATION_LIMIT
    )
    offset = max(request.args.get('offset', default=0, type=int), 0)
 
    # Query the database
    results = execute_neo4j_query(
        """
        MATCH (c:City)
        RETURN c
        ORDER BY c.created_at DESC SKIP $offset
        LIMIT $limit
        """,
        {'offset': offset, 'limit': limit},
        many=True,
    )
 
    # Process the results
    schema = CitySchema()
    return APIResponse.success(
        payload={
            'data': [schema.dump(item.get('c')) for item in results],
            'pagination': {},
        },
    )

def find_city_by_postal_code(postal_code):
    """
    Tìm city theo postal_code. Trả về node city nếu tồn tại, ngược lại trả về None.
    """
    result = execute_neo4j_query(
        "MATCH (c:City {postal_code: $postal_code}) RETURN c",
        {'postal_code': postal_code}
    )
    if result and len(result) > 0:
        return result[0]['c']
    return None

def drop_neo4j_database():
    """Delete all nodes and relationships in the Neo4j database."""
    result = execute_neo4j_query("MATCH (n) DETACH DELETE n", {})
    return {'message': 'Neo4j database dropped.'}


def test_create_city():
    schema = CitySchema()
    test_data = {
        'name': 'Hoi An',
        'postal_code': '51000',
    }
    result = execute_neo4j_query(
        """
        MERGE (c:City {postal_code: $postal_code})
        SET c.id = $id, c.created_at = $created_at, c.name = $name
        RETURN c
        """,
        {
            'id': str(uuid.uuid4()),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'name': test_data['name'],
            'postal_code': test_data['postal_code'],
        },
    )
    if not result:
        return {'success': False, 'error': 'Something went wrong'}
    return {'success': True, 'city': schema.dump(result.single()['c'])}


def test_get_cities():
    limit = 10
    offset = 0
    records = execute_neo4j_query(
        """
        MATCH (c:City)
        RETURN c
        ORDER BY c.created_at DESC SKIP $offset
        LIMIT $limit
        """,
        {'offset': offset, 'limit': limit},
    )
    schema = CitySchema()
    return [schema.dump(record['c']) for record in records]