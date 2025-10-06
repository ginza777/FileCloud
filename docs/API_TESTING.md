# FileFinder API Testing and Configuration

## Environment Variables

The application uses the following key environment variables:

### MAIN_URL Configuration
- **Local Development**: `MAIN_URL=http://localhost:8000`
- **Production**: `MAIN_URL=https://fayltop.cloud`

This variable is used by the frontend JavaScript to make API requests to the correct base URL.

## API Endpoints

All API endpoints are tested and working:

### 1. Top Downloads API
- **URL**: `GET /api/files/api/top-downloads/`
- **Description**: Returns top 9 most downloaded files
- **Response**: JSON with `results` array and `total` count

### 2. Search API
- **URL**: `GET /api/files/api/search/?q={query}`
- **Description**: Search files by query string
- **Response**: JSON with `results` array and `total` count
- **Error Handling**: Returns 400 for empty queries

### 3. View Count API
- **URL**: `POST /api/files/api/{product_id}/view/`
- **Description**: Increment view count for a product
- **Response**: JSON with `success: true`

### 4. Download Count API
- **URL**: `POST /api/files/api/{product_id}/download/`
- **Description**: Increment download count for a product
- **Response**: JSON with `success: true`

## Testing

Run comprehensive API tests:

```bash
# Test local environment
docker-compose exec web python /app/test.py --local

# Test production environment
docker-compose exec web python /app/test.py --production

# Test custom URL
docker-compose exec web python /app/test.py --url https://your-domain.com
```

## Test Results

All API endpoints are working correctly:
- ✅ Main page loads with proper styling
- ✅ Top downloads API returns sorted results
- ✅ Search API works with various queries
- ✅ View count increment works
- ✅ Download count increment works
- ✅ Error handling for invalid requests

## Frontend Integration

The frontend JavaScript automatically uses the MAIN_URL setting:
- API requests are made to `${MAIN_URL}/api/files/api/...`
- Telegram bot redirects work correctly
- File preview modals function properly
- Search functionality is responsive

## Production Deployment

For production deployment:
1. Set `MAIN_URL=https://fayltop.cloud` in environment variables
2. Ensure all API endpoints are accessible
3. Run tests to verify functionality
4. Monitor API performance and error rates
