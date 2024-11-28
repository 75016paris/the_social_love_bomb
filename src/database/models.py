# src/database/models.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timedelta

Base = declarative_base()

class Bot(Base):
    __tablename__ = 'bots'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)  # Changed to VARCHAR(50)
    identity = Column(Text, nullable=False)
    rss_url = Column(Text, nullable=False)  # Changed to TEXT
    api_key = Column(String(100), nullable=False)
    api_secret = Column(String(100), nullable=False)
    access_token = Column(String(100), nullable=False)  # Ensure nullable=False if required
    access_token_secret = Column(String(100), nullable=False)  # Same here
    bearer_token = Column(String(100))  # Removed the trailing comma
    user_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationship with tweets
    tweets = relationship("Tweet", back_populates="bot")

class Tweet(Base):
    __tablename__ = 'tweets'

    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer, ForeignKey('bots.id'), nullable=False)
    original_title = Column(Text, nullable=False)
    original_description = Column(Text)
    generated_tweet = Column(Text, nullable=False)
    tweet_id = Column(String(50))  # Changed to VARCHAR(50)
    created_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=False)

    # Relationship with bot
    bot = relationship("Bot", back_populates="tweets")