from flask import Blueprint

from .cities import bp as cities_bp
from .location import bp as location_bp

bp = Blueprint('admin', __name__, url_prefix='/admin')

# Register blueprints
bp.register_blueprint(cities_bp)
bp.register_blueprint(location_bp)
