# src/add_or_update_bots.py

import os
import sys
from pathlib import Path
import re
from typing import Optional, Dict
import logging
import tweepy  # Importez tweepy ici
from database.db_manager import DatabaseManager
from database.models import Bot

sys.path.append(str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

class BotConfigManager:
    def __init__(self):
        self.db = DatabaseManager()
        # Get the root directory of the project
        self.project_root = Path(__file__).resolve().parent.parent
        self.bots_config_dir = self.project_root / "my_bots"
        
    def parse_bot_file(self, file_path: Path) -> Optional[Dict]:
        """Parse a bot configuration file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            def extract_section(section_name: str) -> str:
                # Log the raw content that is being processed
                logger.debug(f"Extracting section: {section_name}")
                pattern = r'{}.*?"""(.*?)"""'.format(re.escape(section_name))  # Correct pattern for multi-line content
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    extracted_content = match.group(1).strip()
                    logger.debug(f"Extracted content for {section_name}: {extracted_content}")  # Log extracted content
                    return extracted_content
                else:
                    logger.debug(f"No match for {section_name}")
                return ""
            
            config = {
                'name': extract_section("1. Name of your bot"),
                'identity': extract_section("2. Bot Persona"),
                'rss_url': extract_section("4. Rss url"),
                'api_key': extract_section("5. Api Key"),
                'api_secret': extract_section("6. Api secret"),
                'access_token': extract_section("7. Access Token"),
                'access_token_secret': extract_section("8. Access Token Secret"),
                'bearer_token': extract_section("9. Bearer Token")
            }

            # Debugging log: print extracted sections
            logger.info(f"Extracted config: {config}")
            logger.info(f"Parsed config for {file_path.name}: {config}")

            # Check if required fields are present
            if not all([config['name'], config['identity'], config['rss_url'], config['api_key'], config['api_secret'], config['access_token'], config['access_token_secret']]):
                logger.error(f"Missing required fields in {file_path}")
                return None

            return config

        except Exception as e:
            logger.error(f"Error parsing bot file {file_path}: {e}")
            return None

    def update_or_create_bot(self, config: Dict) -> bool:
        try:
            session = self.db.get_session()
            existing_bot = session.query(Bot).filter_by(name=config['name']).first()

            if existing_bot:
                # Update existing bot
                for key, value in config.items():
                    if value:
                        setattr(existing_bot, key, value)
                
                bot = existing_bot
                logger.info(f"Bot {config['name']} updated successfully")
            else:
                # Create new bot
                bot = Bot(
                    name=config['name'],
                    identity=config['identity'],
                    rss_url=config['rss_url'],
                    api_key=config['api_key'],
                    api_secret=config['api_secret'], 
                    access_token=config['access_token'],
                    access_token_secret=config['access_token_secret'],
                    bearer_token=config['bearer_token'],
                    is_active=True
                )
                session.add(bot)
                logger.info(f"Bot {config['name']} created successfully")

            # Save bot to get ID
            session.commit()

            # Get and update user_id if not set
            if not bot.user_id:
                user_id = self.get_user_id(bot, config['api_key'], 
                                            config['api_secret'],
                                            config['access_token'], 
                                            config['access_token_secret'])
                if user_id:
                    bot.user_id = user_id
                    session.commit()
                    logger.info(f"Updated user_id for bot {bot.name}")

            return True

        except Exception as e:
            logger.error(f"Error updating/creating bot {config['name']}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def get_user_id(self, bot, api_key, api_secret, access_token, access_token_secret):
        """Retrieve the user_id for the bot from Twitter."""
        try:
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret
            )
            
            response = client.get_me()  # Get the bot's Twitter user info
            
            if response.data:
                return response.data['id']
            else:
                logger.error(f"Failed to retrieve user ID for {bot.name}")
                return None
        except Exception as e:
            logger.error(f"Error retrieving user ID for {bot.name}: {e}")
            return None
    
    def sync_bots(self):
        """Synchronize all configuration files with the database."""
        if not self.bots_config_dir.exists():
            logger.error(f"Bots config directory not found: {self.bots_config_dir}")
            return
            
        logger.info("Starting bot synchronization...")
        
        # Loop through all configuration files
        for file_path in self.bots_config_dir.glob('*'):
            if file_path.is_file() and not file_path.name.startswith('.'):
                logger.info(f"Processing bot file: {file_path.name}")
                config = self.parse_bot_file(file_path)
                
                if config:
                    self.update_or_create_bot(config)
                else:
                    logger.error(f"Failed to parse bot file: {file_path}")
        
        logger.info("Bot synchronization completed")
        
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Run synchronization
    bot_manager = BotConfigManager()
    bot_manager.sync_bots()