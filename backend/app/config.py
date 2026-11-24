import os
from threading import Lock
import yaml
from app.utils.custom_error import CustomError
from dotenv import load_dotenv

load_dotenv()

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

FILES_CONVERTED_DIR = os.path.join(BASE_PATH, "files_converted")
FILES_GENERATED_DIR = os.getenv("GCAI_ARTIFACT_DIR", os.path.join(BASE_PATH, "files_generated"))
MODEL_PATH = os.getenv("GCAI_MODEL_PATH", os.path.join(BASE_PATH, "models", "model_files", "160_model.pth"))
GLYPHS_CONFIG_PATH = os.path.join(BASE_PATH, "data_configs", "glyphs.yaml")

try:
    with open(GLYPHS_CONFIG_PATH, "r") as file:
        data_configs = yaml.safe_load(file)
except FileNotFoundError:
    raise RuntimeError(f"Configuration file not found: {GLYPHS_CONFIG_PATH}")
except yaml.YAMLError as e:
    raise RuntimeError(f"Error parsing YAML file: {e}")

NUM_CLASSES = data_configs.get("NC", 0)
CLASSES = data_configs.get("CLASSES", [])
THRESHOLD = 0.7
DEVICE = None


def _secret(name):
    path = os.getenv(name + "_FILE")
    if path:
        with open(path) as stream:
            return stream.read().rstrip("\r\n")
    return os.getenv(name)


DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": _secret("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "raise_on_warnings": True,
}


def load_model():
    """
    Loads and initializes the ML model using the checkpoint from the specified MODEL_PATH.
    """
    try:
        from app.checkpoint import verified_checkpoint

        with verified_checkpoint(MODEL_PATH, os.getenv("GCAI_EXPECTED_CHECKPOINT_SHA256")) as stream:
            return _load_verified_model(stream)
    except Exception as e:
        raise CustomError(f"Error loading the model: {e}", 500) from None


def _load_verified_model(stream):
    import torch
    from app.models.create_fasterrcnn_model import create_model

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(stream, map_location=device, weights_only=False)
    build_model = create_model[checkpoint["model_name"]]
    model = build_model(num_classes=NUM_CLASSES, pretrained=False, coco_model=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    return model.to(device).eval()


def get_db_connection():
    """Establece una conexión a la base de datos y la devuelve."""
    import mysql.connector
    from mysql.connector import Error

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        raise RuntimeError(f"Database connection failed: {e}")


model = None
_model_lock = Lock()


def get_model():
    """Initialize one detector per process; failed loads remain retryable."""
    global model
    if model is None:
        with _model_lock:
            if model is None:
                loaded = load_model()
                if loaded is None:
                    raise CustomError("Model not loaded", 500)
                model = loaded
    return model
