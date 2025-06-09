# User Management API Documentation

## Overview

This document describes the comprehensive user management API for the Da Nang travel website. The API provides full CRUD operations for user management with proper authentication, authorization, validation, and pagination.

## Database Changes

### New User Fields
- `birthday` (DATE, nullable): User's date of birth
- `phone_number` (VARCHAR(20), nullable): User's phone number

### Migration Applied
```sql
-- Migration: Add birthday and phone_number to users
ALTER TABLE users ADD COLUMN birthday DATE;
ALTER TABLE users ADD COLUMN phone_number VARCHAR(20);
```

## API Endpoints

### Authentication
All endpoints require JWT authentication via the `Authorization: Bearer <token>` header.

### Base URL
```
/api/users
```

## Endpoints

### 1. Get Users with Pagination and Search

```http
GET /api/users/
```

**Description**: Get a paginated list of users with optional name search and sorting.

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Query Parameters:**
- `page` (optional): Page number (default: 1, min: 1)
- `size` (optional): Items per page (default: 10, min: 1, max: 100)
- `name` (optional): Search by full name or email (case-insensitive partial match)
- `order_by` (optional): Sort field - `created_at`, `full_name`, `email`, `updated_at` (default: `created_at`)
- `order_direction` (optional): Sort direction - `asc`, `desc` (default: `desc`)

**Example Request:**
```bash
curl -X GET "http://localhost:5000/api/users/?page=1&size=10&name=john&order_by=full_name&order_direction=asc" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response:**
```json
{
  "data": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "avatar": "https://example.com/avatar.jpg",
      "email": "john.doe@example.com",
      "is_admin": false,
      "is_verified": true,
      "full_name": "John Doe",
      "birthday": "1990-05-15",
      "phone_number": "+84 123 456 789",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-06-01T14:20:00Z"
    }
  ],
  "paging": {
    "page": 1,
    "size": 10,
    "offset": 0,
    "totalCount": 25,
    "pageCount": 3
  }
}
```

### 2. Get User Detail

```http
GET /api/users/<user_id>
```

**Description**: Get detailed information about a specific user including statistics.

**Path Parameters:**
- `user_id`: UUID of the user

**Example Request:**
```bash
curl -X GET "http://localhost:5000/api/users/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "avatar": "https://example.com/avatar.jpg",
  "email": "john.doe@example.com",
  "is_admin": false,
  "is_verified": true,
  "full_name": "John Doe",
  "birthday": "1990-05-15",
  "phone_number": "+84 123 456 789",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-06-01T14:20:00Z",
  "statistics": {
    "favorites_count": 12,
    "reviews_count": 8,
    "trips_count": 3,
    "average_rating_given": 4.2
  }
}
```

### 3. Update User

```http
PATCH /api/users/<user_id>
```

**Description**: Update user information (partial update). Users can only update themselves, admins can update any user.

**Path Parameters:**
- `user_id`: UUID of the user

**Request Body (all fields optional):**
```json
{
  "avatar": "https://example.com/new-avatar.jpg",
  "full_name": "John Smith",
  "birthday": "1990-05-15",
  "phone_number": "+84 987 654 321"
}
```

**Validation Rules:**
- `full_name`: 2-100 characters
- `birthday`: Cannot be in the future
- `phone_number`: Max 20 characters, only digits, spaces, hyphens, and plus signs

**Example Request:**
```bash
curl -X PATCH "http://localhost:5000/api/users/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Smith",
    "phone_number": "+84 987 654 321"
  }'
```

**Example Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "avatar": "https://example.com/avatar.jpg",
  "email": "john.doe@example.com",
  "is_admin": false,
  "is_verified": true,
  "full_name": "John Smith",
  "birthday": "1990-05-15",
  "phone_number": "+84 987 654 321",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-06-02T15:45:00Z"
}
```

### 4. Delete User

```http
DELETE /api/users/<user_id>
```

**Description**: Delete a user. Users can delete themselves, admins can delete any user. Cannot delete the last admin.

**Path Parameters:**
- `user_id`: UUID of the user

**Example Request:**
```bash
curl -X DELETE "http://localhost:5000/api/users/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response:**
```json
{
  "message": "User deleted successfully",
  "deleted_user": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "full_name": "John Doe",
    "email": "john.doe@example.com"
  }
}
```

### 5. Get Current User

```http
GET /api/users/me
```

**Description**: Get the currently authenticated user's information.

**Example Request:**
```bash
curl -X GET "http://localhost:5000/api/users/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "avatar": "https://example.com/avatar.jpg",
  "email": "john.doe@example.com",
  "is_admin": false,
  "is_verified": true,
  "full_name": "John Doe",
  "birthday": "1990-05-15",
  "phone_number": "+84 123 456 789",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-06-01T14:20:00Z"
}
```

### 6. Update Current User

```http
PATCH /api/users/me
```

**Description**: Update the currently authenticated user's information.

**Request Body (all fields optional):**
```json
{
  "avatar": "https://example.com/new-avatar.jpg",
  "full_name": "John Smith",
  "birthday": "1990-05-15",
  "phone_number": "+84 987 654 321"
}
```

**Example Request:**
```bash
curl -X PATCH "http://localhost:5000/api/users/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Smith",
    "birthday": "1990-05-15"
  }'
```

## Error Responses

### 400 Bad Request
```json
{
  "error": "Validation failed",
  "details": {
    "birthday": ["Birthday cannot be in the future"],
    "phone_number": ["Phone number must contain only digits, spaces, hyphens, and plus signs"]
  }
}
```

### 401 Unauthorized
```json
{
  "error": "Unauthorized"
}
```

### 403 Forbidden
```json
{
  "error": "Permission denied"
}
```

### 404 Not Found
```json
{
  "error": "User not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Failed to get users"
}
```

## Authorization Rules

1. **Get Users**: Any authenticated user
2. **Get User Detail**: Any authenticated user
3. **Update User**: 
   - Users can update themselves
   - Admins can update any user
4. **Delete User**: 
   - Users can delete themselves
   - Admins can delete any user
   - Cannot delete the last admin
5. **Get/Update Current User**: Any authenticated user

## Testing Examples

### 1. Test Pagination and Search

```bash
# Get first page of users
curl -X GET "http://localhost:5000/api/users/?page=1&size=5" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Search users by name
curl -X GET "http://localhost:5000/api/users/?name=john" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Sort users by name ascending
curl -X GET "http://localhost:5000/api/users/?order_by=full_name&order_direction=asc" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 2. Test User CRUD Operations

```bash
# Get user detail
curl -X GET "http://localhost:5000/api/users/USER_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Update user profile
curl -X PATCH "http://localhost:5000/api/users/USER_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Updated Name",
    "birthday": "1985-12-25",
    "phone_number": "+84 123 456 789"
  }'

# Update current user
curl -X PATCH "http://localhost:5000/api/users/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+84 987 654 321"
  }'
```

### 3. Test Error Scenarios

```bash
# Invalid pagination parameters
curl -X GET "http://localhost:5000/api/users/?page=0&size=101" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Invalid phone number format
curl -X PATCH "http://localhost:5000/api/users/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "invalid-phone-number"
  }'

# Future birthday
curl -X PATCH "http://localhost:5000/api/users/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "birthday": "2030-01-01"
  }'
```

## Integration with Existing System

The user management API integrates seamlessly with:

1. **Authentication System**: Uses existing JWT authentication
2. **Database Models**: Extends existing User model with new fields
3. **Validation**: Uses Marshmallow schemas for consistent validation
4. **Error Handling**: Follows existing error handling patterns
5. **Logging**: Integrates with application logging system

## Performance Considerations

1. **Pagination**: All user listings are paginated to prevent large result sets
2. **Indexing**: Consider adding database indexes on frequently searched fields
3. **Caching**: Consider implementing Redis caching for frequently accessed user data
4. **Validation**: Input validation happens before database operations

## Security Features

1. **Authorization**: Role-based access control (users vs admins)
2. **Input Validation**: Comprehensive validation for all input fields
3. **SQL Injection Protection**: Uses SQLAlchemy ORM for database queries
4. **Admin Protection**: Prevents deletion of the last admin user
5. **Privacy**: Password fields are never included in API responses

This user management API provides a robust foundation for managing users in the Da Nang travel application with proper security, validation, and performance considerations. 