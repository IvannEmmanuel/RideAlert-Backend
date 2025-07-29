# Background Model Loading

## Overview

To solve the problem of users waiting 2-5 minutes for model downloads on their first prediction request, this backend now implements **background model loading**. Models are downloaded and loaded automatically when the server starts, so predictions are instant once ready.

## How It Works

### 1. Server Startup

-   When FastAPI starts, it automatically begins downloading and loading the 590MB of ML models in the background
-   The server is immediately available for other requests
-   Users can check loading progress via status endpoints

### 2. Background Process

-   Models are downloaded from Google Drive URLs (configured in `.env`)
-   Progress is tracked and can be monitored
-   If download fails, it can be retried
-   Loading happens in a separate thread, not blocking the main server

### 3. Prediction Behavior

-   **Before models ready**: Returns HTTP 202 with "still loading" message
-   **After models ready**: Instant predictions (no download delay)
-   **On error**: Returns HTTP 503 with error details

## API Endpoints

### Check Server Status

```bash
GET /status
```

Returns overall server and model loading status.

### Check Prediction Readiness

```bash
GET /predict/status
```

Returns detailed prediction service status:

-   `ready`: Models loaded, predictions available
-   `loading`: Models downloading/loading in background
-   `error`: Loading failed
-   `not_started`: Loading hasn't begun (shouldn't happen)

### Make Predictions

```bash
POST /predict
```

-   **If ready**: Returns prediction immediately
-   **If loading**: Returns HTTP 202 "still loading, try again later"
-   **If error**: Returns HTTP 503 with error details

## Client Integration

### Simple Approach

Just call `/predict` and handle the status codes:

```python
response = requests.post("/predict", json=data)
if response.status_code == 202:
    # Models still loading, try again later
    print("Models loading, please wait...")
elif response.status_code == 200:
    # Success!
    result = response.json()
```

### Smart Waiting

Use the status endpoint to wait intelligently:

```python
# Check if ready
status = requests.get("/predict/status").json()
if status["status"] == "loading":
    print("Waiting for models to load...")
    # Poll until ready
```

### Full Example

See `client_example.py` for a complete implementation that:

-   Checks server status
-   Waits for models to load
-   Makes predictions once ready

## Deployment Benefits

### Free Tier Compatibility

-   **No timeout issues**: Models load in background, server stays responsive
-   **Health checks pass**: Server is healthy even while models load
-   **Graceful degradation**: Clear status messages instead of hanging requests

### Production Advantages

-   **Better UX**: No 5-minute wait for first user
-   **Monitoring**: Clear status endpoints for health checks
-   **Reliability**: Retry mechanisms and error handling
-   **Scalability**: One-time download per container instance

## Configuration

Models are downloaded from URLs specified in `.env`:

```bash
MODEL_GRADIENT_BOOSTING_URL=https://drive.google.com/uc?id=your_file_id
MODEL_RANDOM_FOREST_URL=https://drive.google.com/uc?id=your_file_id
# ... etc
```

## Development vs Production

### Development

-   Models download once when you start the server
-   Subsequent restarts are fast (models cached locally)
-   Use `/models/clear` to force re-download if needed

### Production

-   Each container instance downloads models once on startup
-   Models persist in container until restart
-   Consider pre-building containers with models for even faster startup

## Monitoring

### Health Checks

```bash
GET /health
```

Returns model loading status for monitoring systems.

### Model Management

```bash
GET /models/status     # Detailed file and loading status
POST /models/reload    # Force reload models
DELETE /models/clear   # Delete models (for testing)
```

## Migration from Synchronous Loading

### Before (Synchronous)

```python
# First prediction triggers 5-minute download
response = requests.post("/predict", json=data)  # 5 minutes wait
```

### After (Background)

```python
# Server starts, models load in background
# First prediction is either instant (if ready) or deferred (if loading)
response = requests.post("/predict", json=data)  # Instant response
```

The key improvement is that **users never wait for downloads** - they either get instant predictions or a clear "still loading" message.
