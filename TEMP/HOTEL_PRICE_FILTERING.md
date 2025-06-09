# Hotel Price Filtering - Updated Approach

## Overview

The hotel API has been updated to use more flexible `min_price` and `max_price` parameters instead of the previous `price_levels` approach. This provides better user experience and more precise filtering capabilities.

## API Changes

### Old Approach (Deprecated)
```
GET /api/hotels?price_levels=3
```
This used a hardcoded mapping:
- 1: "$1 - $25"
- 2: "$26 - $50" 
- 3: "$51 - $75"
- 4: "$76 - $100"
- 5: "$101+"

### New Approach
```
GET /api/hotels?min_price=50&max_price=100
GET /api/hotels?min_price=101  # For $101+ hotels
GET /api/hotels?max_price=50   # For hotels up to $50
```

## Database Schema Changes

### Neo4j Properties Added
- `min_price` (Integer): Minimum price extracted from price_range string
- `max_price` (Integer): Maximum price extracted from price_range string, null for "$X+" format

### Price Range Examples
| Original price_range | min_price | max_price |
|---------------------|-----------|-----------|
| "$1 - $25"          | 1         | 25        |
| "$26 - $50"         | 26        | 50        |
| "$101+"             | 101       | null      |

## API Response Changes

### Hotel Response Fields
All hotel responses now include:
```json
{
  "element_id": "...",
  "name": "Hotel Name",
  "price_range": "$50 - $75",
  "min_price": 50,
  "max_price": 75,
  // ... other fields
}
```

## Migration

### Running the Migration
```bash
python migrate_hotel_prices.py
```

This script:
1. Reads all hotels with `price_range` values
2. Extracts numeric `min_price` and `max_price` 
3. Updates Neo4j nodes with these properties
4. Provides summary of updated records

### Backward Compatibility
- The `price_range` string field is preserved
- If Neo4j properties are missing, the API falls back to runtime extraction
- The `price_levels` relationship is still maintained but not used for filtering

## Filter Logic

### Min Price Filter
```cypher
(h.min_price IS NOT NULL AND h.min_price >= $min_price) OR
(h.min_price IS NULL AND h.max_price IS NOT NULL AND h.max_price >= $min_price)
```

### Max Price Filter  
```cypher
(h.max_price IS NOT NULL AND h.max_price <= $max_price) OR
(h.max_price IS NULL AND h.min_price IS NOT NULL AND h.min_price <= $max_price)
```

### Combined Filters
```
GET /api/hotels?min_price=50&max_price=100&rating=4.0&hotel_class=3
```

## Examples

### Filter hotels between $50-$100
```bash
curl "https://your-api.com/api/hotels?min_price=50&max_price=100"
```

### Filter hotels $101 and above
```bash
curl "https://your-api.com/api/hotels?min_price=101"
```

### Filter hotels up to $50
```bash
curl "https://your-api.com/api/hotels?max_price=50"
```

### Combined with other filters
```bash
curl "https://your-api.com/api/hotels?min_price=75&rating=4.5&hotel_class=4"
```

## Benefits

1. **Flexibility**: Users can specify any price range, not limited to predefined levels
2. **Performance**: Direct numeric comparison in Neo4j instead of string parsing
3. **Precision**: Exact price matching instead of category matching
4. **User Experience**: More intuitive parameters that match user expectations
5. **Extensibility**: Easy to add additional price-based features in the future

## Error Handling

- Invalid price values are ignored
- Missing price properties fall back to string extraction
- Cache keys include price parameters for proper cache invalidation
- Search and filter modes remain mutually exclusive 