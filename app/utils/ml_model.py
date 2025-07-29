import joblib
import os
from typing import Any, Dict
from .model_downloader import ensure_models_exist

ML_DIR = os.path.join(os.path.dirname(__file__), '../ml')


class MLModelManager:
    def __init__(self):
        self.models = {}
        self.scaler = None
        self.features = None
        self.label_encoders = None
        self._models_loaded = False

    def are_models_available(self):
        """Quick check if all model files exist locally"""
        required_files = [
            "app/ml/enhanced_features_v6.pkl",
            "app/ml/enhanced_label_encoders_v6.pkl",
            "app/ml/gradient_boosting_model_v6.pkl",
            "app/ml/random_forest_model_v6.pkl",
            "app/ml/robust_scaler_v6.pkl"
        ]
        return all(os.path.exists(f) for f in required_files)

    def _load_all_optimized(self):
        """Memory-optimized model loading for Railway deployment"""
        print("🔧 Starting memory-optimized model loading...")
        
        # Ensure models are downloaded first
        ensure_models_exist()
        
        try:
            import gc  # For garbage collection
            
            print("📦 Loading models one by one to optimize memory...")
            
            # Load scaler first (smallest)
            print("🔧 Loading scaler...")
            self.scaler = self._load_pickle('robust_scaler_v6.pkl')
            gc.collect()
            
            # Load features
            print("🔧 Loading features...")
            self.features = self._load_pickle('enhanced_features_v6.pkl')
            gc.collect()
            
            # Load label encoders
            print("🔧 Loading label encoders...")
            self.label_encoders = self._load_pickle('enhanced_label_encoders_v6.pkl')
            gc.collect()
            
            # Load only one model to start (gradient boosting is usually smaller)
            print("🔧 Loading gradient boosting model...")
            self.models['gradient_boosting'] = self._load_pickle('gradient_boosting_model_v6.pkl')
            gc.collect()
            
            # Load random forest (larger model)
            print("🔧 Loading random forest model...")
            self.models['random_forest'] = self._load_pickle('random_forest_model_v6.pkl')
            gc.collect()
            
            print("✅ Memory-optimized model loading completed!")
            self._models_loaded = True
            
        except Exception as e:
            print(f"❌ Memory-optimized loading failed: {e}")
            raise

    def _load_all(self):
        """Load all models, downloading them first if needed"""
        print("Initializing ML models...")

        # Ensure models are downloaded first
        ensure_models_exist()

        try:
            print("Loading models...")
            self.models['gradient_boosting'] = self._load_pickle(
                'gradient_boosting_model_v6.pkl')
            self.models['random_forest'] = self._load_pickle(
                'random_forest_model_v6.pkl')
            self.scaler = self._load_pickle('robust_scaler_v6.pkl')
            self.features = self._load_pickle('enhanced_features_v6.pkl')
            self.label_encoders = self._load_pickle(
                'enhanced_label_encoders_v6.pkl')

            print("✅ All models loaded successfully")
            self._models_loaded = True

            # Print valid classes for each label-encoded feature
            if self.label_encoders:
                for feat, encoder in self.label_encoders.items():
                    print(
                        f"Valid classes for '{feat}': {list(encoder.classes_)}")

        except Exception as e:
            print(f"❌ Error loading models: {e}")
            raise

    def _load_pickle(self, filename):
        """Load pickle file with memory optimization"""
        import gc
        with open(os.path.join(ML_DIR, filename), 'rb') as f:
            result = joblib.load(f)
        gc.collect()  # Force garbage collection after each load
        return result

    def _load_all(self):
        """Load all models with memory optimization for Railway"""
        import gc
        print("🧠 Initializing ML models with memory optimization...")

        # Ensure models are downloaded first
        ensure_models_exist()

        try:
            print("📦 Loading models one by one with garbage collection...")
            
            # Load models sequentially with garbage collection between each
            print("Loading gradient boosting model...")
            self.models['gradient_boosting'] = self._load_pickle('gradient_boosting_model_v6.pkl')
            
            print("Loading random forest model...")
            self.models['random_forest'] = self._load_pickle('random_forest_model_v6.pkl')
            
            print("Loading scaler...")
            self.scaler = self._load_pickle('robust_scaler_v6.pkl')
            
            print("Loading features...")
            self.features = self._load_pickle('enhanced_features_v6.pkl')
            
            print("Loading label encoders...")
            self.label_encoders = self._load_pickle('enhanced_label_encoders_v6.pkl')

            print("✅ All models loaded successfully with memory optimization")
            self._models_loaded = True

            # Print valid classes for each label-encoded feature
            if self.label_encoders:
                for feat, encoder in self.label_encoders.items():
                    print(f"Valid classes for '{feat}': {list(encoder.classes_)}")

        except MemoryError as me:
            print(f"💾 Memory error during model loading: {me}")
            print("⚠️ Railway memory limit exceeded - consider upgrading plan")
            raise MemoryError("Railway memory limit exceeded during model loading")
        except Exception as e:
            print(f"❌ Error loading models: {e}")
            raise

    def preprocess(self, input_data: Dict[str, Any]):
        X = [input_data[feat] for feat in self.features]
        for i, feat in enumerate(self.features):
            if feat in self.label_encoders:
                X[i] = self.label_encoders[feat].transform([X[i]])[0]
        X_scaled = self.scaler.transform([X])[0]
        return X_scaled

    def predict(self, input_data: Dict[str, Any], model_name: str = 'gradient_boosting'):
        if not self._models_loaded:
            self._load_all()

        X_scaled = self.preprocess(input_data)
        model = self.models.get(model_name)
        if not model:
            raise ValueError(f"Model '{model_name}' not found.")
        prediction = model.predict([X_scaled])[0]
        # Ensure output is JSON serializable
        if hasattr(prediction, 'tolist'):
            prediction = prediction.tolist()
        return prediction


ml_manager = MLModelManager()
