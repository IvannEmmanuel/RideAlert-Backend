# ML Models Directory

This directory contains machine learning models that are downloaded at runtime from external storage.

## Model Files (Downloaded Automatically):

-   `enhanced_features_v6.pkl` - Feature list and ordering
-   `enhanced_label_encoders_v6.pkl` - Categorical feature encoders
-   `gradient_boosting_model_v6.pkl` - Gradient boosting prediction model
-   `random_forest_model_v6.pkl` - Random forest prediction model
-   `robust_scaler_v6.pkl` - Feature scaling transformer

Models are automatically downloaded on first prediction request from Google Drive URLs specified in environment variables.

## Environment Variables Required:

-   `ENHANCED_FEATURES_V6`
-   `ENHANCED_LABEL_ENCODERS_V6`
-   `GRADIENT_BOOSTING_MODEL_V6`
-   `RANDOM_FOREST_MODEL_V6`
-   `ROBUST_SCALER_V6`
