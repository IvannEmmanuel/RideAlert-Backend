#!/bin/bash
# Railway startup script

# Use Railway's PORT environment variable or default to 8000
PORT=${PORT:-8000}

echo "🚀 Starting FastAPI server on port $PORT"
echo "📁 Current directory: $(pwd)"
echo "📋 Python path: $PYTHONPATH"
echo "📦 Checking main.py exists..."

if [ ! -f "main.py" ]; then
    echo "❌ main.py not found!"
    ls -la
    exit 1
fi

echo "✅ main.py found"
echo "🔧 Testing Python imports..."

# Test if we can import the main module
python -c "
try:
    import main
    print('✅ Successfully imported main module')
    print('✅ App object:', hasattr(main, 'app'))
except Exception as e:
    print('❌ Error importing main module:', str(e))
    import traceback
    traceback.print_exc()
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Import test failed, exiting..."
    exit 1
fi

echo "🚀 Starting uvicorn server..."
exec uvicorn main:app --host 0.0.0.0 --port $PORT
