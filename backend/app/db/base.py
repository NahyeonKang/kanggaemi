"""
app/db/base.py

Shared SQLAlchemy declarative base.
Import this in every ORM model file.
"""
from sqlalchemy.orm import declarative_base

Base = declarative_base()
