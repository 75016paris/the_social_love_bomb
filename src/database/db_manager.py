# src/database/db_manager.py
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging
from pathlib import Path
from datetime import datetime
from .models import Tweet, Bot, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_name="bots.db"):
        try:
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / db_name
            
            logger.info(f"Initializing database at: {db_path}")
            
            # Create engine and bind session
            self.engine = create_engine(f'sqlite:///{db_path}', echo=True)
            self.Session = sessionmaker()
            self.Session.configure(bind=self.engine)
            
            # Create tables
            Base.metadata.create_all(self.engine)
            
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def get_session(self):
        try:
            return self.Session()
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise

    def ensure_tables_exist(self):
        """Check if tables exist, create if they don't"""
        inspector = inspect(self.engine)
        if 'bots' not in inspector.get_table_names():
            return self.init_db()
        return True

    def update_user_id(self, bot_id: int, user_id: str) -> bool:
        session = self.get_session()
        try:
            bot = session.query(Bot).filter_by(id=bot_id).first()
            if bot:
                bot.user_id = user_id
                session.commit()
                logger.info(f"User ID for bot {bot.name} updated successfully")
                return True
            else:
                logger.error(f"Bot with ID {bot_id} not found")
                return False
        except SQLAlchemyError as e:
            logger.error(f"Error updating user ID for bot {bot_id}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def get_session(self):
        return self.Session()

    def get_active_bots(self):
        session = self.get_session()
        try:
            return session.query(Bot).filter_by(is_active=True).all()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving active bots: {e}")
            return []
        finally:
            session.close()

    def is_title_tweeted(self, title):
        session = self.get_session()
        try:
            tweet = session.query(Tweet).filter_by(original_title=title).first()
            return bool(tweet)
        except SQLAlchemyError as e:
            logger.error(f"Error checking tweet status: {e}")
            return False
        finally:
            session.close()

    def save_tweet(self, bot_id, original_title, original_description, generated_tweet, tweet_id, success):
        session = self.get_session()
        try:
            tweet = Tweet(
                bot_id=bot_id,
                original_title=original_title,
                original_description=original_description,
                generated_tweet=generated_tweet,
                tweet_id=tweet_id,
                success=success,
                created_at=datetime.utcnow()
            )
            session.add(tweet)
            session.commit()
            logger.info(f"Tweet saved successfully for bot_id {bot_id}")
        except SQLAlchemyError as e:
            logger.error(f"Error saving tweet: {e}")
            session.rollback()
        finally:
            session.close()