import json
import logging
import numpy as np
from collections import defaultdict, Counter
from typing import List, Dict, Optional, Tuple
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import fields, ValidationError, validates
from app.extensions import ma
from app.models import UserFavourite, UserReview, VectorItem, db
from app.utils import execute_neo4j_query, get_redis, create_paging
from geopy.distance import geodesic

logger = logging.getLogger(__name__)
blueprint = Blueprint('recommendations', __name__, url_prefix='/recommendations')


class RecommendationSchema(ma.Schema):
    created_at = fields.String(dump_only=True)
    element_id = fields.String(dump_only=True)
    description = fields.String(dump_only=True, allow_none=True)
    image = fields.String(dump_only=True)
    is_favorite = fields.Boolean(dump_only=True, default=False)
    latitude = fields.Float(dump_only=True)
    longitude = fields.Float(dump_only=True)
    name = fields.String(dump_only=True)
    phone = fields.String(dump_only=True, allow_none=True)
    photos = fields.List(fields.String(), dump_only=True, default=list)
    rating = fields.Float(dump_only=True, allow_none=True)
    rating_histogram = fields.List(fields.Integer(), dump_only=True, default=list)
    raw_ranking = fields.Float(dump_only=True)
    street = fields.String(dump_only=True, allow_none=True)
    subcategories = fields.List(fields.String(), dump_only=True, default=list)
    subtypes = fields.List(fields.String(), dump_only=True, default=list)
    website = fields.String(dump_only=True, allow_none=True)
    type = fields.String(dump_only=True)
    similarity_score = fields.Float(dump_only=True)
    recommendation_reason = fields.String(dump_only=True)


class RecommendationQuerySchema(ma.Schema):
    place_type = fields.String(
        required=False,
        missing='all',
        validate=lambda x: x in ['all', 'hotels', 'restaurants', 'things-to-do']
    )
    limit = fields.Integer(required=False, missing=10, validate=lambda x: 1 <= x <= 50)
    exclude_visited = fields.Boolean(required=False, missing=True)
    min_rating = fields.Float(required=False, missing=0.0, validate=lambda x: 0.0 <= x <= 5.0)
    user_lat = fields.Float(required=False, allow_none=True)
    user_lng = fields.Float(required=False, allow_none=True)
    max_distance_km = fields.Float(required=False, allow_none=True, validate=lambda x: x > 0)

    @validates('user_lat')
    def validate_latitude(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise ValidationError('Latitude must be between -90 and 90')
        return value

    @validates('user_lng')
    def validate_longitude(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise ValidationError('Longitude must be between -180 and 180')
        return value


def get_user_preferences(user_id: str) -> Dict:
    """Get user preferences from favorites and reviews."""
    try:
        # Get user's favorite places
        favorites_result = db.session.execute(
            db.text("SELECT place_id FROM user_favourites WHERE user_id = :user_id"),
            {'user_id': user_id}
        )

        favorite_place_ids = [row.place_id for row in favorites_result]
        # print("favorite_place_ids")
        # print(favorite_place_ids)
        # Get user's reviews with ratings
        reviews_result = db.session.execute(
            db.text("SELECT place_id, rating FROM user_reviews WHERE user_id = :user_id"),
            {'user_id': user_id}
        )
        reviews = {row.place_id: row.rating for row in reviews_result}
        # print("reviews")
        # print(reviews)
        # Get place details from Neo4j for favorites and reviewed places
        all_place_ids = list(set(favorite_place_ids + list(reviews.keys())))
        
        if not all_place_ids:
            return {
                'subcategories': {},
                'subtypes': {},
                'avg_rating_preference': 0.0,
                'place_count': 0,
                'favorite_places': [],
                'reviewed_places': {}
            }

        # Get place details from Neo4j
        neo4j_query = """
        UNWIND $place_ids AS pid
        MATCH (p) WHERE elementId(p) = pid
        OPTIONAL MATCH (p)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        OPTIONAL MATCH (p)-[:HAS_SUBTYPE]->(st:Subtype)
        RETURN elementId(p) AS place_id, 
               collect(DISTINCT sc.name) AS subcategories,
               collect(DISTINCT st.name) AS subtypes,
               p.rating AS place_rating
        """
        
        places_data = execute_neo4j_query(neo4j_query, {'place_ids': all_place_ids})
        print("places_data")
        print(places_data)
        if not places_data:
            return {
                'subcategories': {},
                'subtypes': {},
                'avg_rating_preference': 0.0,
                'place_count': 0,
                'favorite_places': [],
                'reviewed_places': {}
            }

        # Analyze preferences
        subcategory_scores = defaultdict(float)
        subtype_scores = defaultdict(float)
        total_weight = 0

        for place in places_data:
            place_id = place['place_id']
            
            # Weight: favorites = 2.0, high ratings (4-5) = 1.5, medium ratings (3) = 1.0, low ratings (1-2) = 0.5
            weight = 2.0 if place_id in favorite_place_ids else 0.0
            
            if place_id in reviews:
                rating = reviews[place_id]
                if rating >= 4:
                    weight += 1.5
                elif rating == 3:
                    weight += 1.0
                else:
                    weight += 0.5
            
            total_weight += weight
            
            # Add subcategory preferences
            for subcategory in place['subcategories']:
                if subcategory:  # Skip empty strings
                    subcategory_scores[subcategory] += weight

            # Add subtype preferences
            for subtype in place['subtypes']:
                if subtype:  # Skip empty strings
                    subtype_scores[subtype] += weight

        # Normalize scores
        if total_weight > 0:
            subcategory_scores = {k: v/total_weight for k, v in subcategory_scores.items()}
            subtype_scores = {k: v/total_weight for k, v in subtype_scores.items()}

        # Calculate average rating preference
        user_ratings = list(reviews.values())
        avg_rating_preference = np.mean(user_ratings) if user_ratings else 0.0

        return {
            'subcategories': dict(subcategory_scores),
            'subtypes': dict(subtype_scores),
            'avg_rating_preference': avg_rating_preference,
            'place_count': len(all_place_ids),
            'favorite_places': favorite_place_ids,
            'reviewed_places': reviews
        }

    except Exception as e:
        logger.error(f"Error getting user preferences: {str(e)}")
        return {
            'subcategories': {},
            'subtypes': {},
            'avg_rating_preference': 0.0,
            'place_count': 0,
            'favorite_places': [],
            'reviewed_places': {}
        }


def calculate_content_similarity(place: Dict, user_prefs: Dict) -> Tuple[float, str]:
    """Calculate content-based similarity score between a place and user preferences."""
    try:
        score = 0.0
        reasons = []

        # Subcategory similarity (40% weight)
        subcategory_score = 0.0
        place_subcategories = place.get('subcategories', [])
        if place_subcategories and user_prefs['subcategories']:
            for subcategory in place_subcategories:
                if subcategory in user_prefs['subcategories']:
                    subcategory_score += user_prefs['subcategories'][subcategory]
            subcategory_score = min(subcategory_score, 1.0)  # Cap at 1.0
            if subcategory_score > 0:
                reasons.append(f"Category match ({subcategory_score:.1f})")

        # Subtype similarity (40% weight)
        subtype_score = 0.0
        place_subtypes = place.get('subtypes', [])
        if place_subtypes and user_prefs['subtypes']:
            for subtype in place_subtypes:
                if subtype in user_prefs['subtypes']:
                    subtype_score += user_prefs['subtypes'][subtype]
            subtype_score = min(subtype_score, 1.0)  # Cap at 1.0
            if subtype_score > 0:
                reasons.append(f"Type match ({subtype_score:.1f})")

        # Rating similarity (20% weight)
        rating_score = 0.0
        place_rating = place.get('rating', 0.0) or 0.0
        if user_prefs['avg_rating_preference'] > 0:
            rating_diff = abs(place_rating - user_prefs['avg_rating_preference'])
            rating_score = max(0, 1 - (rating_diff / 5.0))  # Normalized difference
            if rating_score > 0.6:
                reasons.append(f"Rating match ({place_rating:.1f}★)")

        # Calculate weighted score
        score = (subcategory_score * 0.4) + (subtype_score * 0.4) + (rating_score * 0.2)
        
        # Bonus for high-rated places
        if place_rating >= 4.5:
            score += 0.1
            reasons.append("Highly rated")

        reason = ", ".join(reasons) if reasons else "Popular place"
        
        return score, reason

    except Exception as e:
        logger.error(f"Error calculating content similarity: {str(e)}")
        return 0.0, "Error in calculation"


def get_collaborative_recommendations(user_id: str, place_type: str, limit: int) -> List[Dict]:
    """Get recommendations based on collaborative filtering (users with similar preferences)."""
    try:
        # Find users with similar preferences (based on common favorites)
        similar_users_query = """
        SELECT f2.user_id, COUNT(*) as common_favorites
        FROM user_favourites f1
        JOIN user_favourites f2 ON f1.place_id = f2.place_id
        WHERE f1.user_id = :user_id AND f2.user_id != :user_id
        GROUP BY f2.user_id
        HAVING COUNT(*) >= 2
        ORDER BY common_favorites DESC
        LIMIT 20
        """
        
        similar_users_result = db.session.execute(
            db.text(similar_users_query), {'user_id': user_id}
        )
        similar_user_ids = [row.user_id for row in similar_users_result]

        if not similar_user_ids:
            return []

        # Get places liked by similar users (but not by current user)
        user_places_query = """
        SELECT place_id FROM user_favourites WHERE user_id = :user_id
        UNION
        SELECT place_id FROM user_reviews WHERE user_id = :user_id
        """
        user_places_result = db.session.execute(
            db.text(user_places_query), {'user_id': user_id}
        )
        user_place_ids = [row.place_id for row in user_places_result]

        # Get recommendations from similar users
        placeholders = ', '.join([f':user_{i}' for i in range(len(similar_user_ids))])
        user_params = {f'user_{i}': uid for i, uid in enumerate(similar_user_ids)}
        
        collaborative_query = f"""
        SELECT place_id, COUNT(*) as recommendation_count
        FROM (
            SELECT place_id FROM user_favourites WHERE user_id IN ({placeholders})
            UNION ALL
            SELECT place_id FROM user_reviews WHERE user_id IN ({placeholders}) AND rating >= 4
        ) AS recommended_places
        GROUP BY place_id
        ORDER BY recommendation_count DESC
        LIMIT :limit
        """
        
        params = {**user_params, 'limit': limit * 2}  # Get more to filter later
        collab_result = db.session.execute(db.text(collaborative_query), params)
        
        recommended_place_ids = [
            row.place_id for row in collab_result 
            if row.place_id not in user_place_ids  # Exclude places user already knows
        ]

        if not recommended_place_ids:
            return []

        # Get place details from Neo4j
        type_filter = ""
        if place_type != 'all':
            if place_type == 'things-to-do':
                type_filter = "AND p:ThingToDo"
            elif place_type == 'hotels':
                type_filter = "AND p:Hotel"
            elif place_type == 'restaurants':
                type_filter = "AND p:Restaurant"

        neo4j_query = f"""
        UNWIND $place_ids AS pid
        MATCH (p) WHERE elementId(p) = pid {type_filter}
        OPTIONAL MATCH (p)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        OPTIONAL MATCH (p)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        RETURN p AS place, 
               elementId(p) AS element_id,
               collect(DISTINCT sc.name) AS subcategories,
               collect(DISTINCT st.name) AS subtypes,
               c AS city
        LIMIT $limit
        """

        places_data = execute_neo4j_query(
            neo4j_query, 
            {'place_ids': recommended_place_ids[:limit], 'limit': limit}
        )

        # Format results
        recommendations = []
        for place_data in places_data:
            place = place_data['place']
            place['element_id'] = place_data['element_id']
            place['subcategories'] = [sc for sc in place_data['subcategories'] if sc]
            place['subtypes'] = [st for st in place_data['subtypes'] if st]
            place['similarity_score'] = 0.8  # High score for collaborative filtering
            place['recommendation_reason'] = "Liked by users with similar taste"
            if place_data.get('city'):
                place['city'] = place_data['city']
            recommendations.append(place)

        return recommendations

    except Exception as e:
        logger.error(f"Error getting collaborative recommendations: {str(e)}")
        return []


def get_content_based_recommendations(user_id: str, place_type: str, limit: int, user_prefs: Dict) -> List[Dict]:
    """Get recommendations based on content similarity."""
    try:
        # Get user's known places to exclude
        user_places_query = """
        SELECT place_id FROM user_favourites WHERE user_id = :user_id
        UNION
        SELECT place_id FROM user_reviews WHERE user_id = :user_id
        """
        user_places_result = db.session.execute(
            db.text(user_places_query), {'user_id': user_id}
        )
        user_place_ids = [row.place_id for row in user_places_result]

        # Build Neo4j query based on place type
        type_filter = ""
        if place_type == 'things-to-do':
            type_filter = "p:ThingToDo"
        elif place_type == 'hotels':
            type_filter = "p:Hotel"
        elif place_type == 'restaurants':
            type_filter = "p:Restaurant"
        else:
            type_filter = "p:ThingToDo OR p:Hotel OR p:Restaurant"

        # Get places with subcategories and subtypes
        neo4j_query = f"""
        MATCH (p) WHERE ({type_filter})
        OPTIONAL MATCH (p)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        OPTIONAL MATCH (p)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        WITH p, 
             elementId(p) AS element_id,
             collect(DISTINCT sc.name) AS subcategories,
             collect(DISTINCT st.name) AS subtypes,
             c
        WHERE NOT elementId(p) IN $excluded_places
        AND p.rating IS NOT NULL
        RETURN p AS place, 
               element_id,
               subcategories,
               subtypes,
               c AS city
        ORDER BY p.rating DESC, p.raw_ranking DESC
        LIMIT $limit_multiplier
        """

        excluded_places = user_place_ids if user_place_ids else ['']
        places_data = execute_neo4j_query(
            neo4j_query, 
            {
                'excluded_places': excluded_places,
                'limit_multiplier': limit * 3  # Get more to calculate similarity and then filter
            }
        )

        if not places_data:
            return []

        # Calculate similarity scores
        scored_places = []
        for place_data in places_data:
            place = place_data['place']
            place['element_id'] = place_data['element_id']
            place['subcategories'] = [sc for sc in place_data['subcategories'] if sc]
            place['subtypes'] = [st for st in place_data['subtypes'] if st]
            
            similarity_score, reason = calculate_content_similarity(place, user_prefs)
            place['similarity_score'] = similarity_score
            place['recommendation_reason'] = reason
            
            if place_data.get('city'):
                place['city'] = place_data['city']
                
            scored_places.append(place)

        # Sort by similarity score and return top results
        scored_places.sort(key=lambda x: x['similarity_score'], reverse=True)
        return scored_places[:limit]

    except Exception as e:
        logger.error(f"Error getting content-based recommendations: {str(e)}")
        return []


def get_popular_recommendations(place_type: str, limit: int, excluded_places: List[str] = None) -> List[Dict]:
    """Get popular places as fallback recommendations."""
    try:
        excluded_places = excluded_places or ['']
        
        # Build Neo4j query based on place type
        type_filter = ""
        if place_type == 'things-to-do':
            type_filter = "p:ThingToDo"
        elif place_type == 'hotels':
            type_filter = "p:Hotel"
        elif place_type == 'restaurants':
            type_filter = "p:Restaurant"
        else:
            type_filter = "p:ThingToDo OR p:Hotel OR p:Restaurant"

        neo4j_query = f"""
        MATCH (p) WHERE ({type_filter})
        OPTIONAL MATCH (p)-[:HAS_SUBCATEGORY]->(sc:Subcategory)
        OPTIONAL MATCH (p)-[:HAS_SUBTYPE]->(st:Subtype)
        OPTIONAL MATCH (p)-[:LOCATED_IN]->(c:City)
        WITH p, 
             elementId(p) AS element_id,
             collect(DISTINCT sc.name) AS subcategories,
             collect(DISTINCT st.name) AS subtypes,
             c
        WHERE NOT elementId(p) IN $excluded_places
        AND p.rating IS NOT NULL
        RETURN p AS place, 
               element_id,
               subcategories,
               subtypes,
               c AS city
        ORDER BY p.rating DESC, p.raw_ranking DESC
        LIMIT $limit
        """

        places_data = execute_neo4j_query(
            neo4j_query, 
            {'excluded_places': excluded_places, 'limit': limit}
        )

        recommendations = []
        for place_data in places_data:
            place = place_data['place']
            place['element_id'] = place_data['element_id']
            place['subcategories'] = [sc for sc in place_data['subcategories'] if sc]
            place['subtypes'] = [st for st in place_data['subtypes'] if st]
            place['similarity_score'] = 0.5  # Medium score for popular places
            place['recommendation_reason'] = "Popular in Da Nang"
            
            if place_data.get('city'):
                place['city'] = place_data['city']
                
            recommendations.append(place)

        return recommendations

    except Exception as e:
        logger.error(f"Error getting popular recommendations: {str(e)}")
        return []


def apply_filters(places: List[Dict], filters: Dict) -> List[Dict]:
    """Apply additional filters to recommendations."""
    try:
        filtered_places = places.copy()

        # Apply minimum rating filter
        if filters.get('min_rating', 0.0) > 0:
            filtered_places = [
                place for place in filtered_places 
                if (place.get('rating') or 0.0) >= filters['min_rating']
            ]

        # Apply distance filter if user location is provided
        if (filters.get('user_lat') is not None and 
            filters.get('user_lng') is not None and 
            filters.get('max_distance_km') is not None):
            
            user_location = (filters['user_lat'], filters['user_lng'])
            max_distance = filters['max_distance_km']
            
            distance_filtered = []
            for place in filtered_places:
                if place.get('latitude') is not None and place.get('longitude') is not None:
                    place_location = (place['latitude'], place['longitude'])
                    distance = geodesic(user_location, place_location).kilometers
                    if distance <= max_distance:
                        distance_filtered.append(place)
            
            filtered_places = distance_filtered

        return filtered_places

    except Exception as e:
        logger.error(f"Error applying filters: {str(e)}")
        return places


@blueprint.get('/')
@jwt_required(optional=True)
def get_recommendations():
    """Get personalized recommendations for the current user."""
    try:
        # Validate query parameters
        schema = RecommendationQuerySchema()
        try:
            args = schema.load(request.args)
        except ValidationError as e:
            return jsonify({'error': 'Invalid parameters', 'details': e.messages}), 400

        user_id = get_jwt_identity()
        place_type = args['place_type']
        limit = args['limit']

        # Check cache first
        cache_key = f"recommendations:{user_id}:{place_type}:{limit}"
        try:
            redis = get_redis()
            cached_data = redis.get(cache_key)
            if cached_data:
                logger.info(f"Returning cached recommendations for user {user_id}")
                return jsonify(json.loads(cached_data)), 200
        except Exception as e:
            logger.warning(f"Redis cache error: {str(e)}")

        # Get user preferences
        user_prefs = get_user_preferences(user_id)
        # print("user_prefs")
        # print(user_prefs)
        recommendations = []
        
        # If user has enough interaction data, use hybrid approach
        if user_prefs['place_count'] >= 3:
            # Get collaborative filtering recommendations (30%)
            collab_recs = get_collaborative_recommendations(user_id, place_type, max(2, limit // 3))
            recommendations.extend(collab_recs)
            # print("collab_recs")
            # print(collab_recs)

            # Get content-based recommendations (50%)
            content_limit = max(3, limit - len(collab_recs))
            content_recs = get_content_based_recommendations(user_id, place_type, content_limit, user_prefs)
            recommendations.extend(content_recs)
            # print("content_recs")
            # print(content_recs)

        # Fill remaining slots with popular places
        current_place_ids = [place['element_id'] for place in recommendations]
        remaining_limit = limit - len(recommendations)
        
        if remaining_limit > 0:
            popular_recs = get_popular_recommendations(place_type, remaining_limit, current_place_ids)
            recommendations.extend(popular_recs)
            print("popular_recs")
            print(popular_recs)


        # Remove duplicates and maintain order
        seen_ids = set()
        unique_recommendations = []
        for place in recommendations:
            place_id = place['element_id']
            if place_id not in seen_ids:
                seen_ids.add(place_id)
                unique_recommendations.append(place)

        # print("unique_recommendations")
        # print(unique_recommendations)

        # Apply additional filters
        filtered_recommendations = apply_filters(unique_recommendations, args)

        # Limit final results
        final_recommendations = filtered_recommendations[:limit]

        # print("final_recommendations")
        # print(final_recommendations)

        # Check if places are in user's favorites
        if final_recommendations:
            user_favorites = db.session.execute(
                db.text("SELECT place_id FROM user_favourites WHERE user_id = :user_id"),
                {'user_id': user_id}
            )
            favorite_place_ids = set(row.place_id for row in user_favorites)
            
            for place in final_recommendations:
                place['is_favorite'] = place['element_id'] in favorite_place_ids

        # Serialize and cache results
        schema = RecommendationSchema(many=True)
        result = schema.dump(final_recommendations)
        
        # Cache for 30 minutes
        try:
            redis = get_redis()
            redis.setex(cache_key, 1800, json.dumps(result))
        except Exception as e:
            logger.warning(f"Failed to cache recommendations: {str(e)}")

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        return jsonify({'error': 'Failed to get recommendations'}), 500


@blueprint.post('/refresh')
@jwt_required()
def refresh_user_recommendations():
    """Refresh/invalidate cached recommendations for the current user."""
    try:
        user_id = get_jwt_identity()
        
        # Clear all cached recommendations for this user
        try:
            redis = get_redis()
            pattern = f"recommendations:{user_id}:*"
            keys_to_delete = redis.keys(pattern)
            if keys_to_delete:
                redis.delete(*keys_to_delete)
                logger.info(f"Cleared {len(keys_to_delete)} cached recommendations for user {user_id}")
        except Exception as e:
            logger.warning(f"Redis cache error: {str(e)}")

        return jsonify({'message': 'Recommendations cache refreshed successfully'}), 200

    except Exception as e:
        logger.error(f"Error refreshing recommendations: {str(e)}")
        return jsonify({'error': 'Failed to refresh recommendations'}), 500


@blueprint.get('/stats')
@jwt_required()
def get_user_recommendation_stats():
    """Get statistics about user's preferences for debugging/analysis."""
    try:
        user_id = get_jwt_identity()
        user_prefs = get_user_preferences(user_id)
        print(user_prefs)
        stats = {
            'total_interactions': user_prefs['place_count'],
            'favorite_places_count': len(user_prefs['favorite_places']),
            'reviewed_places_count': len(user_prefs['reviewed_places']),
            'average_rating_given': user_prefs['avg_rating_preference'],
            'top_subcategories': dict(Counter(user_prefs['subcategories']).most_common(5)),
            'top_subtypes': dict(Counter(user_prefs['subtypes']).most_common(5)),
            'recommendation_strategy': 'hybrid' if user_prefs['place_count'] >= 3 else 'popular_based'
        }
        
        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error getting recommendation stats: {str(e)}")
        return jsonify({'error': 'Failed to get recommendation stats'}), 500 