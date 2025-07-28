import threading
import time
from .ml_model import MLModelManager


class BackgroundModelLoader:
    def __init__(self):
        self.ml_manager = MLModelManager()
        self.loading_thread = None
        self.is_loading = False
        self.load_error = None
        self.load_complete = False

    def start_background_loading(self):
        """Start loading models in the background"""
        if self.is_loading or self.load_complete:
            return

        print("🚀 Starting background model loading...")
        self.is_loading = True
        self.loading_thread = threading.Thread(
            target=self._load_models_background)
        self.loading_thread.daemon = True
        self.loading_thread.start()

    def _load_models_background(self):
        """Load models in background thread"""
        try:
            print("📦 Background: Downloading and loading models...")
            self.ml_manager._load_all()
            self.load_complete = True
            self.is_loading = False
            print("✅ Background model loading completed!")
        except Exception as e:
            print(f"❌ Background model loading failed: {str(e)}")
            self.load_error = str(e)
            self.is_loading = False

    def get_status(self):
        """Get current loading status"""
        if self.load_complete:
            return {"status": "ready", "models_loaded": True}
        elif self.is_loading:
            return {"status": "loading", "models_loaded": False, "message": "Models are being downloaded and loaded in background"}
        elif self.load_error:
            return {"status": "error", "models_loaded": False, "error": self.load_error}
        else:
            return {"status": "not_started", "models_loaded": False}

    def wait_for_models(self, timeout=300):  # 5 minute timeout
        """Wait for models to be ready with timeout"""
        start_time = time.time()
        while not self.load_complete and not self.load_error:
            if time.time() - start_time > timeout:
                raise TimeoutError("Model loading timed out")
            time.sleep(1)

        if self.load_error:
            raise Exception(f"Model loading failed: {self.load_error}")

        return self.ml_manager

    def get_ml_manager(self):
        """Get the ML manager (only if ready)"""
        if self.load_complete:
            return self.ml_manager
        return None


# Global instance
background_loader = BackgroundModelLoader()
