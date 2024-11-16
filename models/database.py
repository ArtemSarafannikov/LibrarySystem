from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from hashlib import sha256


db = SQLAlchemy()


class LDatabase:
    class Users(UserMixin, db.Model):
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(150), nullable=False, unique=True)
        password = db.Column(db.String(150), nullable=False)
        fines = db.Column(db.Float, default=0.0)
        is_admin = db.Column(db.Boolean, default=False)
        is_confirmed = db.Column(db.Boolean, default=False)

    class Books(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(100), nullable=False)
        author = db.Column(db.String(100), nullable=False)
        available = db.Column(db.Boolean, default=True)
        due_days = db.Column(db.Integer, nullable=False, default=7)
        cover_url = db.Column(db.String())
        qr_crypt = db.Column(db.String(), nullable=False, default=sha256(f"{id}{title}".encode()))


    class Reservation(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        reservation_date = db.Column(db.DateTime, default=datetime.utcnow)
        expiration_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=2))

        book = db.relationship('Books', backref=db.backref('reserved_to', lazy=True))
        user = db.relationship('Users', backref=db.backref('reserved_books', lazy=True))

    class UsersBooks(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        issue_date = db.Column(db.DateTime, default=datetime.utcnow)
        return_date = db.Column(db.DateTime)
        deadline_date = db.Column(db.DateTime, nullable=False)

        book = db.relationship('Books', backref=db.backref('issued_to', lazy=True))
        user = db.relationship('Users', backref=db.backref('issued_books', lazy=True))
