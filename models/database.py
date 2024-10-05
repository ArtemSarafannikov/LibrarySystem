from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class LDatabase:
    class Users(UserMixin, db.Model):
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(150), nullable=False, unique=True)
        password = db.Column(db.String(150), nullable=False)
        fines = db.Column(db.Float, default=0.0)
        is_admin = db.Column(db.Boolean, default=False)

    class Books(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(100), nullable=False)
        author = db.Column(db.String(100), nullable=False)
        available = db.Column(db.Boolean, default=True)
