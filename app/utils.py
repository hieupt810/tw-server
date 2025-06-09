import logging
import json
import re

logger = logging.getLogger(__name__)

def create_paging(
    data: list, page: int, size: int, offset: int, total_count: int
):
    page_count = (total_count // size) + (1 if total_count % size > 0 else 0)

    return {
        'data': data,
        'paging': {
            'page': page,
            'size': size,
            'offset': offset,
            'totalCount': total_count,
            'pageCount': page_count,
        },
    }


def execute_neo4j_query(query: str, params: dict = None):
    from neo4j import GraphDatabase

    from .environments import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    try:
        with driver.session() as session:
            result = session.run(query, params)
            if 'RETURN' in query.upper():
                return result.data()
    except Exception as e:
        raise e
    finally:
        driver.close()


def send_async_email(recipients: list[str], subject: str, html: str):
    from threading import Thread

    from flask_mail import Message

    from . import AppContext
    from .extensions import mail

    def send_email(message: Message):
        app = AppContext().get_app()
        with app.app_context():
            mail.send(message)

    # Create a new message
    message = Message(subject=subject, recipients=recipients)
    message.html = html

    # Start a new thread to send the email
    thread = Thread(target=send_email, args=(message,))
    thread.start()


def get_redis():
    from . import AppContext

    return AppContext().get_redis()


def update_place_rating_histogram(place_id: str, old_rating: float = None, new_rating: float = None):
    """
    Update the rating histogram of a place in Neo4j.
    
    Args:
        place_id: The ID of the place
        old_rating: The old rating to remove (if updating or deleting)
        new_rating: The new rating to add (if creating or updating)
    """
    try:
        # Convert ratings to integers (1-5)
        if old_rating is not None:
            old_rating = int(round(old_rating))
        if new_rating is not None:
            new_rating = int(round(new_rating))

        # If updating or deleting, first decrement the old rating
        if old_rating is not None:
            execute_neo4j_query(
                """
                MATCH (p)
                WHERE elementId(p) = $place_id
                WITH p, 
                     CASE WHEN p.rating_histogram IS NULL THEN [0,0,0,0,0] ELSE p.rating_histogram END as hist
                SET p.rating_histogram = [
                    CASE WHEN $rating = 1 AND hist[0] > 0 THEN hist[0] - 1 ELSE hist[0] END,
                    CASE WHEN $rating = 2 AND hist[1] > 0 THEN hist[1] - 1 ELSE hist[1] END,
                    CASE WHEN $rating = 3 AND hist[2] > 0 THEN hist[2] - 1 ELSE hist[2] END,
                    CASE WHEN $rating = 4 AND hist[3] > 0 THEN hist[3] - 1 ELSE hist[3] END,
                    CASE WHEN $rating = 5 AND hist[4] > 0 THEN hist[4] - 1 ELSE hist[4] END
                ]
                """,
                {'place_id': place_id, 'rating': old_rating}
            )
        
        # If creating or updating, increment the new rating
        if new_rating is not None:
            execute_neo4j_query(
                """
                MATCH (p)
                WHERE elementId(p) = $place_id
                WITH p, 
                     CASE WHEN p.rating_histogram IS NULL THEN [0,0,0,0,0] ELSE p.rating_histogram END as hist
                SET p.rating_histogram = [
                    CASE WHEN $rating = 1 THEN hist[0] + 1 ELSE hist[0] END,
                    CASE WHEN $rating = 2 THEN hist[1] + 1 ELSE hist[1] END,
                    CASE WHEN $rating = 3 THEN hist[2] + 1 ELSE hist[2] END,
                    CASE WHEN $rating = 4 THEN hist[3] + 1 ELSE hist[3] END,
                    CASE WHEN $rating = 5 THEN hist[4] + 1 ELSE hist[4] END
                ]
                """,
                {'place_id': place_id, 'rating': new_rating}
            )
        
        # Update the average rating
        execute_neo4j_query(
            """
            MATCH (p)
            WHERE elementId(p) = $place_id
            WITH p, 
                 CASE WHEN p.rating_histogram IS NULL THEN [0,0,0,0,0] ELSE p.rating_histogram END as hist
            SET p.rating = CASE 
                WHEN reduce(total = 0, x IN hist | total + x) > 0 
                THEN round(toFloat(reduce(total = 0, i IN range(0, 4) | total + (i + 1) * hist[i])) / toFloat(reduce(total = 0, x IN hist | total + x)), 1)
                ELSE 0.0 
            END
            RETURN p.rating, p.rating_histogram
            """,
            {'place_id': place_id}
        )
        # # Log the updated rating and histogram for debugging
        # result = execute_neo4j_query(
        #     """
        #     MATCH (p)
        #     WHERE elementId(p) = $place_id
        #     RETURN p.rating, p.rating_histogram
        #     """,
        #     {'place_id': place_id}
        # )
        # print(result)
        # print("--------------------------------")
        # if result:
        #     logger.info(f"Updated rating for place {place_id}: {result[0]['p.rating']}, histogram: {result[0]['p.rating_histogram']}")
        # else:
        #     logger.warning(f"No result found for place {place_id} after updating rating.")
        
        return True
    except Exception as e:
        logger.error(f"Error updating rating histogram: {str(e)}")
        return False


def check_place_exists(place_id: str) -> bool:
    """
    Check if a place exists in Neo4j database.
    
    Args:
        place_id: The ID of the place to check
        
    Returns:
        bool: True if place exists, False otherwise
    """
    try:
        result = execute_neo4j_query(
            """
            MATCH (p)
            WHERE elementId(p) = $place_id
            RETURN count(p) as count
            """,
            {'place_id': place_id}
        )
        return result[0]['count'] > 0
    except Exception as e:
        logger.error(f"Error checking place existence: {str(e)}")
        return False


def update_user_preference_cache(user_id: str):
    """
    Update cached user preferences when user adds favorites or reviews.
    This helps keep recommendations fresh and personalized.
    
    Args:
        user_id: The ID of the user whose preferences need updating
    """
    try:
        redis = get_redis()
        
        # Clear cached recommendations for this user
        pattern = f"recommendations:{user_id}:*"
        keys_to_delete = redis.keys(pattern)
        if keys_to_delete:
            redis.delete(*keys_to_delete)
            logger.info(f"Cleared {len(keys_to_delete)} cached recommendations for user {user_id}")
        
        # Optionally pre-compute and cache user preferences
        from app.models import UserFavourite, UserReview, db
        
        # Get user's favorites and reviews
        favorites_result = db.session.execute(
            db.text("SELECT place_id FROM user_favourites WHERE user_id = :user_id"),
            {'user_id': user_id}
        )
        favorite_place_ids = [row.place_id for row in favorites_result]
        
        reviews_result = db.session.execute(
            db.text("SELECT place_id, rating FROM user_reviews WHERE user_id = :user_id"),
            {'user_id': user_id}
        )
        reviews = {row.place_id: row.rating for row in reviews_result}
        
        # Cache user interaction summary
        interaction_summary = {
            'favorite_count': len(favorite_place_ids),
            'review_count': len(reviews),
            'avg_rating': sum(reviews.values()) / len(reviews) if reviews else 0.0,
            'last_updated': db.session.execute(db.text("SELECT NOW()")).scalar().isoformat()
        }
        
        redis.setex(f"user_summary:{user_id}", 3600, json.dumps(interaction_summary))
        
        return True
    except Exception as e:
        logger.error(f"Error updating user preference cache: {str(e)}")
        return False


def delete_place_and_related_data(place_id: str) -> dict:
    """
    Comprehensively delete a place and all related data from both Neo4j and PostgreSQL.
    
    This function handles:
    - Deleting the place from Neo4j (hotels, restaurants, things-to-do)
    - Removing all relationships (features, price levels, cuisines, etc.)
    - Deleting user reviews from PostgreSQL
    - Removing user favorites from PostgreSQL
    - Removing place from trips in PostgreSQL
    - Clearing all related cache entries
    
    Args:
        place_id: The ID of the place to delete
        
    Returns:
        dict: Summary of deletion operations with counts and status
    """
    from app.models import UserFavourite, UserReview, UserTrip, db
    
    deletion_summary = {
        'place_deleted': False,
        'reviews_deleted': 0,
        'favorites_deleted': 0,
        'trips_updated': 0,
        'cache_cleared': False,
        'errors': []
    }
    
    try:
        # Check if place exists first
        if not check_place_exists(place_id):
            deletion_summary['errors'].append(f"Place with ID {place_id} not found")
            return deletion_summary
        
        # 1. Delete user reviews from PostgreSQL
        try:
            reviews_deleted = db.session.query(UserReview).filter_by(place_id=place_id).delete()
            deletion_summary['reviews_deleted'] = reviews_deleted
            logger.info(f"Deleted {reviews_deleted} reviews for place {place_id}")
        except Exception as e:
            deletion_summary['errors'].append(f"Error deleting reviews: {str(e)}")
        
        # 2. Delete user favorites from PostgreSQL
        try:
            favorites_deleted = db.session.query(UserFavourite).filter_by(place_id=place_id).delete()
            deletion_summary['favorites_deleted'] = favorites_deleted
            logger.info(f"Deleted {favorites_deleted} favorites for place {place_id}")
        except Exception as e:
            deletion_summary['errors'].append(f"Error deleting favorites: {str(e)}")
        
        # 3. Remove place from trips in PostgreSQL
        try:
            # Get all trips that contain this place using the correct Trip model
            from app.models import Trip
            trips_deleted = db.session.query(Trip).filter_by(place_id=place_id).delete()
            deletion_summary['trips_updated'] = trips_deleted
            logger.info(f"Deleted {trips_deleted} trip entries for place {place_id}")
        except Exception as e:
            deletion_summary['errors'].append(f"Error deleting trip entries: {str(e)}")
        
        # Commit PostgreSQL changes
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            deletion_summary['errors'].append(f"Error committing database changes: {str(e)}")
        
        # 4. Delete place and all relationships from Neo4j
        # IMPORTANT: This only deletes the place node and its relationships.
        # It does NOT delete connected nodes like Subtype, Feature, PriceLevel, etc.
        # since those nodes can be shared by multiple places.
        # Example: If a hotel has Feature "WiFi", deleting the hotel will remove
        # the HAS_FEATURE relationship but keep the "WiFi" Feature node for other places.
        try:
            result = execute_neo4j_query(
                """
                MATCH (p)
                WHERE elementId(p) = $place_id
                OPTIONAL MATCH (p)-[r]-()
                DELETE r, p
                RETURN count(p) as deleted_count
                """,
                {'place_id': place_id}
            )
            
            if result and result[0]['deleted_count'] > 0:
                deletion_summary['place_deleted'] = True
                logger.info(f"Successfully deleted place {place_id} from Neo4j")
            else:
                deletion_summary['errors'].append("Failed to delete place from Neo4j")
        except Exception as e:
            deletion_summary['errors'].append(f"Error deleting place from Neo4j: {str(e)}")
        
        # 5. Clear all related cache entries
        try:
            redis = get_redis()
            
            # Clear cache for all place types
            cache_patterns = [
                'hotels:*',
                'restaurants:*',
                'things-to-do:*',
                f'hotels:{place_id}',
                f'restaurants:{place_id}',
                f'things-to-do:{place_id}',
                'reviews:*',
                'recommendations:*'
            ]
            
            total_keys_deleted = 0
            for pattern in cache_patterns:
                keys_to_delete = redis.keys(pattern)
                if keys_to_delete:
                    redis.delete(*keys_to_delete)
                    total_keys_deleted += len(keys_to_delete)
            
            deletion_summary['cache_cleared'] = True
            logger.info(f"Cleared {total_keys_deleted} cache entries related to place {place_id}")
        except Exception as e:
            deletion_summary['errors'].append(f"Error clearing cache: {str(e)}")
        
        # Update user preference caches for affected users
        try:
            # Get all users who had this place in favorites or reviews
            affected_users = set()
            
            # Users who favorited this place
            favorite_users = db.session.execute(
                db.text("SELECT DISTINCT user_id FROM user_favourites WHERE place_id = :place_id"),
                {'place_id': place_id}
            ).fetchall()
            affected_users.update([str(user.user_id) for user in favorite_users])
            
            # Users who reviewed this place
            review_users = db.session.execute(
                db.text("SELECT DISTINCT user_id FROM user_reviews WHERE place_id = :place_id"),
                {'place_id': place_id}
            ).fetchall()
            affected_users.update([str(user.user_id) for user in review_users])
            
            # Update preference cache for each affected user
            for user_id in affected_users:
                update_user_preference_cache(user_id)
            
            logger.info(f"Updated preference cache for {len(affected_users)} affected users")
        except Exception as e:
            deletion_summary['errors'].append(f"Error updating user preference caches: {str(e)}")
        
        return deletion_summary
        
    except Exception as e:
        deletion_summary['errors'].append(f"Unexpected error during deletion: {str(e)}")
        logger.error(f"Error in delete_place_and_related_data: {str(e)}")
        return deletion_summary


def add_price_fields_to_neo4j_hotels():
    """
    One-time utility function to extract min_price and max_price from price_range 
    strings and add them as properties to Hotel nodes in Neo4j.
    
    This should be run once to migrate existing data.
    """
    def extract_price_from_string(price_range_str):
        """Extract min_price and max_price from price_range string."""
        if not price_range_str:
            return None, None
        
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

    try:
        # Get all hotels with price_range
        hotels = execute_neo4j_query(
            """
            MATCH (h:Hotel)
            WHERE h.price_range IS NOT NULL
            RETURN elementId(h) AS hotel_id, h.price_range AS price_range
            """,
            {}
        )
        
        updated_count = 0
        error_count = 0
        
        for hotel in hotels:
            hotel_id = hotel['hotel_id']
            price_range = hotel['price_range']
            
            min_price, max_price = extract_price_from_string(price_range)
            
            try:
                # Update hotel with min_price and max_price
                execute_neo4j_query(
                    """
                    MATCH (h:Hotel)
                    WHERE elementId(h) = $hotel_id
                    SET h.min_price = $min_price, h.max_price = $max_price
                    """,
                    {
                        'hotel_id': hotel_id,
                        'min_price': min_price,
                        'max_price': max_price
                    }
                )
                updated_count += 1
                print(f"Updated hotel {hotel_id} with min_price: {min_price}, max_price: {max_price}")
            except Exception as e:
                print(f"Error updating hotel {hotel_id}: {str(e)}")
                error_count += 1
        
        print(f"Price field migration completed. Updated: {updated_count}, Errors: {error_count}")
        return {'updated': updated_count, 'errors': error_count}
        
    except Exception as e:
        print(f"Error during price field migration: {str(e)}")
        return {'error': str(e)}
