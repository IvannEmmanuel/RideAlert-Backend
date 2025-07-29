#!/bin/bash
# Railway startup script

# Use Railway's PORT environment variable or default to 8000
PORT=${PORT:-8000}

echo "🚀 Starting FastAPI server on port $PORT"
echo "📁 Current directory: $(pwd)"

# Reduced logging to prevent restart loops
if [ ! -f "main.py" ]; then
    echo "❌ main.py not found!"
    exit 1
fi

echo "✅ main.py found, starting server..."

# Start uvicorn directly without import testing to avoid double initialization
exec uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 30
