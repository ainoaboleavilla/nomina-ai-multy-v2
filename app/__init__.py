from pathlib import Path
import os
import secrets
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app():
    # Siempre carga el .env que está en la raíz del proyecto, sin depender
    # de la carpeta desde la que se ejecute `python run.py`.
    load_dotenv(BASE_DIR / ".env", override=False)

    from flask import Flask

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    app.config["UPLOAD_FOLDER"] = str(BASE_DIR / "data")
    app.config["OUTPUT_FOLDER"] = str(BASE_DIR / "data" / "output")

    from .routes import main
    app.register_blueprint(main)
    return app
