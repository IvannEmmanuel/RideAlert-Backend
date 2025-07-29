from fastapi import APIRouter
from app.utils.model_downloader import check_model_status, delete_all_models
from app.utils.background_loader import background_loader

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    status = background_loader.get_status()
    return {
        "status": "healthy",
        "model_status": status["status"],
        "models_loaded": status["models_loaded"]
    }


@router.get("/models/status")
async def model_status():
    """Check status of all model files and loading progress"""
    file_status = check_model_status()
    loader_status = background_loader.get_status()

    return {
        "model_files": file_status,
        "loading_status": loader_status
    }


@router.post("/models/reload")
async def reload_models():
    """Force reload models (useful after manual deletion)"""
    try:
        # Get current ML manager if available
        ml_manager = background_loader.get_ml_manager()

        if ml_manager:
            # Reset the loaded flag to force reload
            ml_manager._models_loaded = False
            ml_manager.models = {}
            ml_manager.scaler = None
            ml_manager.features = None
            ml_manager.label_encoders = None

        # Reset background loader and restart
        background_loader.load_complete = False
        background_loader.load_error = None
        background_loader.is_loading = False

        # Start fresh background loading
        background_loader.start_background_loading()

        return {"message": "Model reload initiated in background", "status": "loading"}
    except Exception as e:
        return {"message": f"Failed to initiate model reload: {str(e)}", "status": "failed"}


@router.delete("/models/clear")
async def clear_models():
    """Delete all model files (for testing/cleanup)"""
    try:
        delete_all_models()

        # Reset background loader state
        background_loader.load_complete = False
        background_loader.load_error = None
        background_loader.is_loading = False

        # Reset in-memory models if available
        ml_manager = background_loader.get_ml_manager()
        if ml_manager:
            ml_manager._models_loaded = False
            ml_manager.models = {}
            ml_manager.scaler = None
            ml_manager.features = None
            ml_manager.label_encoders = None

        return {"message": "All models deleted successfully"}
    except Exception as e:
        return {"message": f"Failed to delete models: {str(e)}"}
