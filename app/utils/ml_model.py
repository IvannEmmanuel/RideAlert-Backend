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
        with open(os.path.join(ML_DIR, filename), 'rb') as f:
            return joblib.load(f)

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
