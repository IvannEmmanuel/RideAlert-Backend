import joblib
import os
from typing import Any, Dict

ML_DIR = os.path.join(os.path.dirname(__file__), '../ml')


class MLModelManager:
    def __init__(self):
        self.models = {}
        self.scaler = None
        self.features = None
        self.label_encoders = None
        self._load_all()

        # Print valid classes for each label-encoded feature
        if self.label_encoders:
            for feat, encoder in self.label_encoders.items():
                print(f"Valid classes for '{feat}': {list(encoder.classes_)}")

    def _load_pickle(self, filename):
        with open(os.path.join(ML_DIR, filename), 'rb') as f:
            return joblib.load(f)

    def _load_all(self):
        self.models['gradient_boosting'] = self._load_pickle(
            'gradient_boosting_model_v6.pkl')
        self.models['random_forest'] = self._load_pickle(
            'random_forest_model_v6.pkl')
        self.scaler = self._load_pickle('robust_scaler_v6.pkl')
        self.features = self._load_pickle('enhanced_features_v6.pkl')
        self.label_encoders = self._load_pickle(
            'enhanced_label_encoders_v6.pkl')

    def preprocess(self, input_data: Dict[str, Any]):
        X = [input_data[feat] for feat in self.features]
        for i, feat in enumerate(self.features):
            if feat in self.label_encoders:
                X[i] = self.label_encoders[feat].transform([X[i]])[0]
        X_scaled = self.scaler.transform([X])[0]
        return X_scaled

    def predict(self, input_data: Dict[str, Any], model_name: str = 'gradient_boosting'):
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
