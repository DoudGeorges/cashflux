"""Flask extensions. Instantiated here to avoid circular imports."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

