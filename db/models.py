# db/models.py
from sqlalchemy import Column, Integer, String, Text, ARRAY, TIMESTAMP
from db.init_db import Base

class GoogleToken(Base):
    __tablename__ = "google_tokens"
    id = Column(Integer, primary_key=True)
    whatsapp_id = Column(String(50), unique=True, index=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_uri = Column(Text)
    client_id = Column(Text)
    client_secret = Column(Text)
    scopes = Column(ARRAY(String))
    expiry = Column(TIMESTAMP)
