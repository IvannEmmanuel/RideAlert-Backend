import os
import requests
from pathlib import Path
import gdown
import time
from tqdm import tqdm


def download_with_progress(url, output_path, timeout=300):
    """Download file with progress bar and timeout"""
    try:
        print(f"🔄 Starting download: {os.path.basename(output_path)}")
        start_time = time.time()

        # Try gdown first (better for Google Drive)
        gdown.download(url, str(output_path), quiet=False)

        download_time = time.time() - start_time
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"✅ Download complete: {size_mb:.1f} MB in {download_time:.1f}s")

    except Exception as e:
        print(f"❌ gdown failed: {e}")
        print("🔄 Trying fallback download...")

        # Fallback to requests with progress
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        with open(output_path, 'wb') as f:
            if total_size > 0:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=os.path.basename(output_path)) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        download_time = time.time() - start_time
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(
            f"✅ Fallback download complete: {size_mb:.1f} MB in {download_time:.1f}s")


def download_models():
    """Download models from URLs defined in environment variables"""
    from dotenv import load_dotenv
    load_dotenv()

    models_dir = Path("app/ml")
    models_dir.mkdir(exist_ok=True)

    # Model URLs from environment variables
    models = {
        "enhanced_features_v6.pkl": os.getenv("ENHANCED_FEATURES_V6"),
        "enhanced_label_encoders_v6.pkl": os.getenv("ENHANCED_LABEL_ENCODERS_V6"),
        "gradient_boosting_model_v6.pkl": os.getenv("GRADIENT_BOOSTING_MODEL_V6"),
        "random_forest_model_v6.pkl": os.getenv("RANDOM_FOREST_MODEL_V6"),
        "robust_scaler_v6.pkl": os.getenv("ROBUST_SCALER_V6")
    }

    print("🚀 Starting model download process...")

    # Check if environment variables are set
    missing_urls = [name for name, url in models.items() if not url]
    if missing_urls:
        print(f"⚠️ Missing environment variables for: {missing_urls}")
        print("📋 Required environment variables:")
        for name in missing_urls:
            env_var = name.replace('.pkl', '').upper()
            print(f"   - {env_var}")
        raise Exception(
            f"Missing environment variables for model URLs: {missing_urls}")

    total_start_time = time.time()

    for model_name, url in models.items():
        if url:
            model_path = models_dir / model_name
            if not model_path.exists():
                try:
                    download_with_progress(url, model_path)
                except Exception as e:
                    print(f"❌ Failed to download {model_name}: {e}")
                    raise
            else:
                size_mb = os.path.getsize(model_path) / (1024 * 1024)
                print(f"✅ {model_name} already exists ({size_mb:.1f} MB)")

    total_time = time.time() - total_start_time
    print(f"🎉 All models ready! Total time: {total_time:.1f}s")


def ensure_models_exist():
    """Ensure all required models are available"""
    required_files = [
        "app/ml/enhanced_features_v6.pkl",
        "app/ml/enhanced_label_encoders_v6.pkl",
        "app/ml/gradient_boosting_model_v6.pkl",
        "app/ml/random_forest_model_v6.pkl",
        "app/ml/robust_scaler_v6.pkl"
    ]

    missing_files = [f for f in required_files if not os.path.exists(f)]

    if missing_files:
        print(f"Missing model files: {missing_files}")
        download_models()
        print("All models downloaded successfully")
    else:
        print("All model files are available")


def check_model_status():
    """Check status of all model files"""
    required_files = [
        "app/ml/enhanced_features_v6.pkl",
        "app/ml/enhanced_label_encoders_v6.pkl",
        "app/ml/gradient_boosting_model_v6.pkl",
        "app/ml/random_forest_model_v6.pkl",
        "app/ml/robust_scaler_v6.pkl"
    ]

    status = {}
    total_size = 0

    for file_path in required_files:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            size_mb = size / (1024 * 1024)
            status[file_path] = f"✅ {size_mb:.1f} MB"
            total_size += size
        else:
            status[file_path] = "❌ Missing"

    print("=== MODEL STATUS ===")
    for file_path, file_status in status.items():
        print(f"{os.path.basename(file_path)}: {file_status}")

    total_mb = total_size / (1024 * 1024)
    print(f"Total size: {total_mb:.1f} MB")

    return status


def delete_all_models():
    """Delete all model files (for testing/cleanup)"""
    model_files = [
        "app/ml/enhanced_features_v6.pkl",
        "app/ml/enhanced_label_encoders_v6.pkl",
        "app/ml/gradient_boosting_model_v6.pkl",
        "app/ml/random_forest_model_v6.pkl",
        "app/ml/robust_scaler_v6.pkl"
    ]

    deleted_count = 0
    for file_path in model_files:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Deleted {os.path.basename(file_path)}")
            deleted_count += 1

    print(f"Deleted {deleted_count} model files")


if __name__ == "__main__":
    # For testing - load environment variables from .env file
    from dotenv import load_dotenv
    load_dotenv()
    download_models()
