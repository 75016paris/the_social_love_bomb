#src/twitter_poster.py

import time
import tweepy
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_api(api_config):
    """
    Creates and returns a Twitter API client with rate limit handling disabled.
    """
    try:
        logger.info(f"Creating API client for API key: {api_config['api_key'][:5]}...")

        # Create the client with wait_on_rate_limit set to False
        client = tweepy.Client(
            bearer_token=api_config['bearer_token'].strip(),
            consumer_key=api_config['api_key'].strip(),
            consumer_secret=api_config['api_secret'].strip(),
            access_token=api_config['access_token'].strip(),
            access_token_secret=api_config['access_token_secret'].strip(),
            wait_on_rate_limit=False  # Changed to False to prevent automatic waiting
        )

        return client

    except Exception as e:
        logger.error(f"Error creating API client for API key: {api_config['api_key'][:5]}. Error: {e}")
        return None

def post_or_reply_to_tweet(bot_name, text, api_config, tweet_id=None):
    """
    Unified function to post a tweet or reply to an existing tweet.
    """
    client = create_api(api_config)
    if not client:
        return False, "API client creation failed"

    # Retrieve the user_id for the bot (this will either be fetched from the DB or from API if necessary)
    bot = bot_manager.db.get_active_bots()[0]  # Assuming we have only one bot here for simplicity
    user_id = bot_manager.get_user_id(bot, client)  # Ensure we use the cached or updated user ID

    # Now proceed with posting the tweet
    request_handler = TwitterRequestHandler(STATUS_DIR)

    try:
        success, tweet_id, error = request_handler.post_tweet(
            bot_name=bot_name,
            client=client,
            text=text[:280],
            reply_to_id=tweet_id
        )

        if success:
            logger.info(f"Tweet posted successfully for {bot_name}")
            return True, tweet_id
        else:
            logger.error(f"Failed to post tweet for {bot_name}: {error}")
            return False, error

    except Exception as e:
        logger.error(f"Error in post_or_reply_to_tweet for {bot_name}: {e}")
        return False, str(e)
    
def get_user_tweets(self, bot, max_results=10):
    try:
        # Ensure bot has a user_id
        if not bot.user_id:
            me = self.client.get_me()
            self.db.update_user_id(bot.id, me.data.id)

        # Ensure max_results is valid (5-100)
        valid_max_results = max(5, min(100, max_results))

        return self.client.get_users_tweets(
            id=bot.user_id,
            max_results=valid_max_results
        )
    except tweepy.errors.TooManyRequests:
        logger.warning(f"Rate limit hit for {bot.name}")
        return None
    except Exception as e:
        logger.error(f"Error getting tweets for {bot.name}: {e}")
        return None
        
def handle_rate_limits(self, response):
    """Handle rate limit headers"""
    if 'x-rate-limit-remaining' in response.headers:
        remaining = int(response.headers['x-rate-limit-remaining'])
        if remaining == 0:
            reset_time = int(response.headers['x-rate-limit-reset'])
            wait_time = reset_time - time.time()
            if wait_time > 0:
                logger.warning(f"Rate limited. Waiting {wait_time} seconds")
                time.sleep(wait_time + 1)