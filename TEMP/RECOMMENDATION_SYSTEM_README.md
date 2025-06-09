# Travel Recommendation System for Da Nang

## Overview

This document describes the comprehensive recommendation system built for the Da Nang travel website. The system provides personalized place recommendations based on user preferences, favorites, and review history using both **content-based filtering** and **collaborative filtering** approaches.

## System Architecture

### Key Components

1. **Content-Based Filtering**: Recommends places similar to ones the user has liked based on:
   - Subcategories (Food & Drink, Classes & Workshops, etc.)
   - Subtypes (Cooking Classes, Museums, etc.)  
   - Rating preferences
   - Location proximity (optional)

2. **Collaborative Filtering**: Recommends places liked by users with similar preferences:
   - Finds users with common favorites
   - Suggests highly-rated places from similar users
   - Excludes places the user already knows about

3. **Hybrid Approach**: Combines both methods for optimal results:
   - 30% collaborative filtering recommendations
   - 50% content-based recommendations  
   - 20% popular/fallback recommendations

4. **Caching & Performance**: 
   - Redis caching for 30-minute recommendation sessions
   - Automatic cache invalidation when user preferences change
   - Pre-computed similarity scores

## API Endpoints

### Main Recommendation Endpoint

```http
GET /api/recommendations/
```

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Query Parameters:**
- `place_type` (optional): `"all"`, `"hotels"`, `"restaurants"`, `"things-to-do"` (default: `"all"`)
- `limit` (optional): Number of recommendations (1-50, default: 10)
- `min_rating` (optional): Minimum place rating filter (0.0-5.0, default: 0.0)
- `user_lat` (optional): User latitude for distance filtering
- `user_lng` (optional): User longitude for distance filtering  
- `max_distance_km` (optional): Maximum distance in kilometers

**Example Request:**
```bash
curl -X GET "http://localhost:5000/api/recommendations/?place_type=things-to-do&limit=5&min_rating=4.0" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response:**
```json
[
  {
    "element_id": "4:0b4c2f30-60c3-48d8-b921-10ce3041ffe4:682",
    "name": "Jolie Cooking Class",
    "description": "Learn to cook real Vietnamese food...",
    "image": "https://media-cdn.tripadvisor.com/media/photo-m/1280/15/26/90/7a/watering-herbs.jpg",
    "latitude": 16.030218,
    "longitude": 108.22827,
    "rating": 5.0,
    "rating_histogram": [0, 0, 0, 2, 870],
    "subcategories": ["Food & Drink", "Classes & Workshops", "Other"],
    "subtypes": ["Cooking Classes"],
    "similarity_score": 0.85,
    "recommendation_reason": "Category match (0.9), Type match (1.0), Highly rated",
    "is_favorite": false,
    "street": "14 An Trung Dong 6",
    "phone": "+84 93 441 43 11",
    "website": "https://joliecookingclass.com/",
    "photos": ["https://...jpg", "..."]
  }
]
```

### Additional Endpoints

#### Refresh User Recommendations
```http
POST /api/recommendations/refresh
```
Clears cached recommendations for immediate refresh.

#### Get User Preference Stats
```http
GET /api/recommendations/stats
```
Returns user preference analysis for debugging/insights.

**Example Stats Response:**
```json
{
  "total_interactions": 12,
  "favorite_places_count": 5,
  "reviewed_places_count": 7,
  "average_rating_given": 4.2,
  "top_subcategories": {
    "Food & Drink": 0.6,
    "Classes & Workshops": 0.4,
    "Outdoor Activities": 0.3
  },
  "top_subtypes": {
    "Cooking Classes": 0.5,
    "Museums": 0.3,
    "Beach Activities": 0.2
  },
  "recommendation_strategy": "hybrid"
}
```

## How It Works

### User Preference Analysis

The system analyzes user behavior to build preference profiles:

1. **Favorites Weight**: 2.0 points per favorite place
2. **Review Ratings Weight**:
   - High ratings (4-5★): 1.5 points
   - Medium ratings (3★): 1.0 points  
   - Low ratings (1-2★): 0.5 points

3. **Category Preferences**: Calculated from subcategories and subtypes of liked places
4. **Rating Preference**: Average of user's given ratings

### Content Similarity Scoring

Places are scored based on similarity to user preferences:

- **Subcategory Match (40%)**: Overlap between place and user preferred subcategories
- **Subtype Match (40%)**: Overlap between place and user preferred subtypes
- **Rating Similarity (20%)**: How close the place rating is to user's average preference
- **Bonus Points**: +0.1 for places rated 4.5★ or higher

### Collaborative Filtering Process

1. Find users with ≥2 common favorites with current user
2. Get places favorited/highly-rated by similar users
3. Exclude places current user already knows
4. Rank by popularity among similar users

### Recommendation Strategy

**For New Users (< 3 interactions):**
- 100% Popular places (highest rated in Da Nang)

**For Experienced Users (≥ 3 interactions):**
- 30% Collaborative filtering recommendations
- 50% Content-based recommendations
- 20% Popular places (fill remaining slots)

## Integration Points

### Automatic Cache Updates

The system automatically refreshes recommendations when users:

- Add/remove favorites → `update_user_preference_cache(user_id)`
- Create/update/delete reviews → `update_user_preference_cache(user_id)`

### Database Integration

**PostgreSQL Tables Used:**
- `user_favourites`: User favorite places
- `user_reviews`: User reviews and ratings
- `vector_items`: Place embeddings (for future semantic search)

**Neo4j Relationships Used:**
- `(Place)-[:HAS_SUBCATEGORY]->(Subcategory)`
- `(Place)-[:HAS_SUBTYPE]->(Subtype)`
- `(Place)-[:LOCATED_IN]->(City)`

## Performance Optimizations

1. **Redis Caching**: 
   - Recommendations cached for 30 minutes
   - User summaries cached for 1 hour
   - Automatic invalidation on preference changes

2. **Query Optimization**:
   - Batch Neo4j queries for place details
   - Limited result sets (max 50 recommendations)
   - Efficient similarity calculations

3. **Background Processing**:
   - Preference cache updates don't block API responses
   - Graceful Redis fallbacks if unavailable

## Testing the System

### 1. Setup Test User with Preferences

```bash
# Add favorites
curl -X POST "http://localhost:5000/api/favourites/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"place_id": "PLACE_ELEMENT_ID"}'

# Add reviews  
curl -X POST "http://localhost:5000/api/reviews/PLACE_ELEMENT_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rating": 5, "review": "Amazing cooking class!"}'
```

### 2. Get Recommendations

```bash
# Get general recommendations
curl -X GET "http://localhost:5000/api/recommendations/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Get specific type with filters
curl -X GET "http://localhost:5000/api/recommendations/?place_type=things-to-do&limit=10&min_rating=4.0" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 3. Analyze User Preferences

```bash
curl -X GET "http://localhost:5000/api/recommendations/stats" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Sample Data Structure

Based on your provided place example, the system processes:

```json
{
  "element_id": "4:0b4c2f30-60c3-48d8-b921-10ce3041ffe4:682",
  "name": "Jolie Cooking Class", 
  "subcategories": ["Food & Drink", "Classes & Workshops", "Other"],
  "subtypes": ["Cooking Classes"],
  "rating": 5.0,
  "latitude": 16.030218,
  "longitude": 108.22827
}
```

## Future Enhancements

1. **Vector Embeddings**: Use `pgvector` for semantic similarity based on descriptions
2. **Machine Learning**: Train models on user interaction patterns
3. **Real-time Learning**: Update preferences based on click-through rates
4. **Social Features**: Friend recommendations and social proof
5. **Seasonal Adjustments**: Account for time-based preferences
6. **Multi-criteria Ranking**: Incorporate weather, events, crowd levels

## Error Handling

The system gracefully handles:
- Redis unavailability (falls back to direct computation)
- Neo4j connection issues (returns error messages)
- Invalid place IDs (404 responses)
- Malformed requests (400 with validation details)
- Authorization failures (401 responses)

## Monitoring & Analytics

Key metrics to track:
- Recommendation click-through rates
- User engagement with recommended places
- Cache hit/miss ratios
- API response times
- User preference evolution over time

This recommendation system provides a robust foundation for personalized travel experiences in Da Nang, combining multiple recommendation techniques with efficient caching and real-time preference learning. 