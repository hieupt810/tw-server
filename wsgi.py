from app import AppContext
from app.environments import DevelopmentConfig
from app.api.admin.cities import drop_neo4j_database, test_create_city, test_get_cities
from app.api.admin.location import test_create_location

app = AppContext().get_app()

if __name__ == '__main__':
    app.config.from_object(DevelopmentConfig)
    # Drop Neo4j database and create test city on server start (for development only)
    # print(drop_neo4j_database())
    # print(test_create_city())
    # print(test_get_cities())
    # print(test_create_location())
    app.run(host='0.0.0.0', port='8000')


