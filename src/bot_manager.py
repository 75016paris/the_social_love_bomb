import tweepy
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import Optional, Dict, Any, Tuple, List
from database.models import Bot, Tweet
from database.db_manager import DatabaseManager
from tweet_generator import generate_spoof, generate_reply

logger = logging.getLogger(__name__)

class BotManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.project_root = Path(__file__).resolve().parent.parent
        self.cache_dir = self.project_root / "bots_twitter_cache"
        self.cache_dir.mkdir(exist_ok=True)

        self.rate_limited: Dict[str, float] = {}  # bot_name -> reset_time
        self.rate_limited_endpoints: Dict[str, Dict[str, float]] = {}  # bot_name -> endpoint -> reset_time
        self.active_bots: List[Bot] = []
        self.current_index = 0

        logger.info(f"Using cache directory: {self.cache_dir}")


    def get_user_id(self, bot: Bot, client) -> str:
        """Retrieve the user ID for the bot if not already cached in the database."""
        
        if bot.user_id:
            logger.info(f"User ID for bot {bot.name} already in the database: {bot.user_id}")
            return bot.user_id  # Return the cached user ID from the database
        
        logger.info(f"User ID not found in database for bot {bot.name}, retrieving from API...")

        try:
            # Retrieve user information from Twitter API if user_id is not cached
            response = self.execute_request(
                bot_name=bot.name,
                request_func=client.get_me,
                endpoint="get_me"
            )

            if response and hasattr(response, 'data') and 'id' in response.data:
                user_id = response.data['id']
                logger.info(f"Retrieved user ID for {bot.name}: {user_id}")

                # Store the user ID in the database for future use
                success = self.db.update_user_id(bot.id, user_id)  # Update the DB with the new user ID
                if success:
                    bot.user_id = user_id  # Update the bot's user_id attribute locally
                    logger.info(f"User ID for {bot.name} saved successfully in the database.")
                    return user_id
                else:
                    logger.error(f"Failed to save user ID for {bot.name}.")
                    return None

            else:
                logger.error(f"Failed to retrieve user ID for bot {bot.name} from API.")
                return None

        except Exception as e:
            logger.error(f"Error retrieving user ID for bot {bot.name}: {e}")
            return None

    # ---------------- Cache Management ----------------
    def _get_cache_file(self, bot_name: str, request_type: str) -> Path:
        return self.cache_dir / f"{bot_name}_{request_type}_cache.json"

    def get_cache(self, bot_name: str, request_type: str) -> Optional[Dict]:
        """Retrieve cached data if available and not expired."""
        cache_file = self._get_cache_file(bot_name, request_type)
        if not cache_file.exists():
            return None
        try:
            with cache_file.open('r') as f:
                cache_data = json.load(f)
            if time.time() > cache_data.get('expires_at', 0):
                logger.info(f"Cache expired for {bot_name} {request_type}.")
                return None
            return cache_data.get('data')
        except json.JSONDecodeError as e:
            logger.error(f"Cache file corrupted: {cache_file}. Error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
            return None

    def set_cache(self, bot_name: str, request_type: str, data: Any, ttl: int = 300):
        """Save data to cache with a specified time-to-live."""
        try:
            cache_file = self._get_cache_file(bot_name, request_type)
            cache_data = {
                'data': data,
                'expires_at': time.time() + ttl,
                'cached_at': time.time()
            }
            with cache_file.open('w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Error writing cache: {e}")

    def clean_expired_cache(self):
        """Remove expired cache files."""
        for cache_file in self.cache_dir.glob("*_cache.json"):
            try:
                with cache_file.open('r') as f:
                    cache_data = json.load(f)
                if time.time() > cache_data.get('expires_at', 0):
                    cache_file.unlink()
            except Exception:
                pass

    # ---------------- Rate Limit Management ----------------
    def mark_rate_limited(self, bot_name: str, endpoint: str, reset_time: float):
        """Mark a bot's specific endpoint as rate-limited."""
        if bot_name not in self.rate_limited_endpoints:
            self.rate_limited_endpoints[bot_name] = {}
        self.rate_limited_endpoints[bot_name][endpoint] = reset_time
        logger.warning(f"Bot {bot_name} rate limited on {endpoint} until {datetime.fromtimestamp(reset_time)}")

    def is_rate_limited(self, bot_name: str, endpoint: str) -> bool:
        """Check if a bot's specific endpoint is currently rate-limited."""
        if bot_name in self.rate_limited_endpoints and endpoint in self.rate_limited_endpoints[bot_name]:
            reset_time = self.rate_limited_endpoints[bot_name][endpoint]
            if time.time() < reset_time:
                return True
            del self.rate_limited_endpoints[bot_name][endpoint]  # Remove expired limit
        return False

    def is_bot_rate_limited(self, bot_name: str) -> bool:
        """Check if a bot is globally rate-limited."""
        if bot_name in self.rate_limited:
            if time.time() < self.rate_limited[bot_name]:
                return True
            del self.rate_limited[bot_name]  # Remove expired limit
        return False

    def clean_expired_limits(self):
        """Clear expired endpoint-specific rate limits."""
        current_time = time.time()
        for bot_name in list(self.rate_limited_endpoints.keys()):
            self.rate_limited_endpoints[bot_name] = {
                endpoint: reset_time
                for endpoint, reset_time in self.rate_limited_endpoints[bot_name].items()
                if current_time < reset_time
            }
            if not self.rate_limited_endpoints[bot_name]:
                del self.rate_limited_endpoints[bot_name]  # Remove empty entries

    def clean_global_expired_limits(self):
        """Clear expired global rate limits."""
        current_time = time.time()
        self.rate_limited = {k: v for k, v in self.rate_limited.items() if current_time < v}

    # ---------------- Twitter API Management ----------------
    def _enforce_rate_limit(self, bot_name: str):
        """Wait until rate limit is lifted for a bot."""
        if self.is_rate_limited(bot_name):
            reset_time = self.rate_limited[bot_name]
            wait_time = max(0, reset_time - time.time())
            if wait_time > 0:
                logger.info(f"Waiting {wait_time:.2f}s for bot {bot_name} rate limit reset.")
                time.sleep(wait_time)

    def _handle_rate_limit_error(self, bot_name: str, endpoint: str, error: tweepy.errors.TooManyRequests) -> int:
        """
        Handle rate limit errors and return the reset time.
        """
        logger.error(f"Rate limit error for bot {bot_name} at endpoint {endpoint}: {error}")
        reset_time = int(time.time() + 900)  # Default fallback reset time

        if hasattr(error, "response") and hasattr(error.response, "headers"):
            headers = error.response.headers
            reset_time = int(headers.get("x-rate-limit-reset", reset_time))
            self.mark_rate_limited(bot_name, endpoint, reset_time)
            logger.info(f"Rate limited until {datetime.fromtimestamp(reset_time)} for bot {bot_name} at endpoint {endpoint}.")

        return reset_time


    def execute_request(self, bot_name: str, request_func: Any, endpoint: str, **kwargs) -> Optional[Any]:
        """Enhanced execute_request with better rate limit handling"""
        retries = 3
        for attempt in range(retries):
            try:
                # Check if we're already rate limited
                if self.is_rate_limited(bot_name, endpoint):
                    reset_time = self.rate_limited_endpoints[bot_name][endpoint]
                    wait_time = max(0, reset_time - time.time())
                    logger.info(f"⏳ Rate limited for {endpoint}, waiting {wait_time:.0f} seconds")
                    time.sleep(wait_time)  # Wait for the rate limit to reset
                    continue  # Try again after waiting

                logger.info(f"🔍 Attempting request for {bot_name} - Endpoint: {endpoint}")
                response = request_func(**kwargs)
                logger.info(f"📥 Response received for {bot_name} - Endpoint: {endpoint}")
                return response

            except tweepy.errors.TooManyRequests as e:
                reset_time = int(time.time() + 900)  # Default 15 minutes
                if hasattr(e, 'response') and 'x-rate-limit-reset' in e.response.headers:
                    reset_time = int(e.response.headers['x-rate-limit-reset'])
                
                wait_time = max(0, reset_time - time.time())
                logger.warning(f"Rate limit hit for {bot_name} on {endpoint}. Waiting {wait_time:.0f} seconds")
                
                self.mark_rate_limited(bot_name, endpoint, reset_time)
                
                if attempt < retries - 1:  # If not the last attempt
                    time.sleep(min(wait_time, 60))  # Wait max 1 minute between retries
                    continue
                return None

            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}/{retries} for {bot_name}, endpoint {endpoint}: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return None

        return None

    # Helper functions

    def _process_rate_limit_headers(self, bot_name: str, endpoint: str, headers: Dict[str, str]):
        """
        Process rate limit headers and update rate-limited status.
        """

    # ---------------- Bot Processing ----------------
    def get_api_client(self, bot: Bot):
        """Create a Twitter API client for a bot."""
        from twitter_poster import create_api
        return create_api({
            'api_key': bot.api_key,
            'api_secret': bot.api_secret,
            'access_token': bot.access_token,
            'access_token_secret': bot.access_token_secret,
            'bearer_token': bot.bearer_token
        })

    def process_article(self, bot: Bot, headline: str, description: str) -> bool:
        """Process and tweet an article."""
        if self.db.is_title_tweeted(headline):
            logger.info(f"Article already processed: {headline[:50]}...")
            return False

        client = self.get_api_client(bot)
        if not client:
            logger.error(f"Failed to create API client for bot {bot.name}.")
            return False

        # Generate tweet content
        tweet_text = generate_spoof(headline=headline, bot_identity=bot.identity)
        if not tweet_text:
            logger.error(f"Failed to generate tweet for {bot.name}")
            return False

        # Post the tweet
        logger.info(f"Attempting to tweet for {bot.name}: {tweet_text[:50]}...")
        response = self.execute_request(
            bot_name=bot.name,
            request_func=client.create_tweet,
            endpoint="post_tweet",
            text=tweet_text[:280]
        )

        if response and hasattr(response, 'data') and 'id' in response.data:
            logger.info(f"Tweet successfully posted: {response.data['id']}")
            self.db.save_tweet(
                bot_id=bot.id,
                original_title=headline,
                original_description=description,
                generated_tweet=tweet_text,
                tweet_id=response.data['id'],
                success=True
            )
            return True
        else:
            logger.error(f"Failed to post tweet. Response: {response}")
            return False


    def process_mentions(self, bot: Bot, next_article: Optional[Tuple[str, str]] = None) -> bool:
        client = self.get_api_client(bot)
        if not client:
            logger.error(f"Failed to create API client for bot {bot.name}.")
            return False

        try:
            # Check if we're rate limited before making the request
            if self.is_rate_limited(bot.name, "get_users_tweets"):
                logger.info(f"Rate limited for get_users_tweets, switching to article processing for {bot.name}")
                if next_article:
                    return self.process_article(bot, next_article[0], next_article[1])
                return False

            # Fetch the last tweets of the bot
            try:
                recent_tweets = self.execute_request(
                    bot_name=bot.name,
                    request_func=client.get_users_tweets,
                    endpoint="get_users_tweets",
                    id=bot.user_id,
                    max_results=5
                )
            except tweepy.errors.TooManyRequests as e:
                logger.warning(f"Rate limit hit for {bot.name}, switching to article processing")
                if next_article:
                    return self.process_article(bot, next_article[0], next_article[1])
                return False

            replies_processed = False
            if recent_tweets and hasattr(recent_tweets, 'data'):
                for tweet in recent_tweets.data:
                    # Check rate limit before searching replies
                    if self.is_rate_limited(bot.name, "search_recent_tweets"):
                        logger.info(f"Rate limited for search_recent_tweets, switching to article for {bot.name}")
                        if next_article:
                            return self.process_article(bot, next_article[0], next_article[1])
                        break

                    try:
                        replies = self.execute_request(
                            bot_name=bot.name,
                            request_func=client.search_recent_tweets,
                            endpoint="search_recent_tweets",
                            query=f"conversation_id:{tweet.id}",
                            max_results=10
                        )

                        if replies and hasattr(replies, 'data') and replies.data:
                            replies_processed = True
                            for reply in replies.data:
                                if reply.author_id != bot.user_id:
                                    response_text = generate_reply(
                                        headline=tweet.text,
                                        bot_identity=bot.identity,
                                        reply_text=reply.text
                                    )
                                    if response_text:
                                        self.execute_request(
                                            bot_name=bot.name,
                                            request_func=client.create_tweet,
                                            endpoint="reply_tweet",
                                            text=response_text,
                                            in_reply_to_tweet_id=reply.id
                                        )

                    except tweepy.errors.TooManyRequests as e:
                        logger.warning(f"Rate limit hit while processing replies for {bot.name}")
                        if next_article:
                            return self.process_article(bot, next_article[0], next_article[1])
                        break

            # If no replies were processed, process the next article
            if not replies_processed and next_article:
                logger.info(f"No replies to process for {bot.name}, processing next article...")
                return self.process_article(bot, next_article[0], next_article[1])

            return True

        except Exception as e:
            logger.error(f"Error processing mentions for bot {bot.name}: {e}")
            if next_article:
                logger.info(f"Switching to article processing due to error for {bot.name}")
                return self.process_article(bot, next_article[0], next_article[1])
            return False


    def fetch_replies_in_batches(self, client, bot_name: str, tweet_id: str, batch_size: int = 10):
        """Fetch replies to a specific tweet in batches."""
        next_token = None
        all_replies = []

        try:
            while True:
                # Perform a batched query for replies
                params = {
                    "query": f"conversation_id:{tweet_id}",
                    "max_results": batch_size,
                    "next_token": next_token
                }
                response = self.execute_request(
                    bot_name=bot_name,
                    request_func=client.search_recent_tweets,
                    endpoint="search_recent_tweets",
                    **params
                )

                if not response or not hasattr(response, 'data') or len(response.data) == 0:
                    break

                all_replies.extend(response.data)

                # Check for pagination token
                next_token = response.meta.get("next_token", None)
                if not next_token:
                    break

        except Exception as e:
            logger.error(f"Error fetching replies in batches for tweet ID {tweet_id}: {e}")

        return all_replies

    def format_time_remaining(self, seconds: int) -> str:
        """Format seconds into a readable time string."""
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
            
        return " ".join(parts)