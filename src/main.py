import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).resolve().parent.parent))

from bot_manager import BotManager
from rss_fetcher import fetch_rss
import time
import random
import signal
import logging
import tweepy
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    print("\nProgram stopping...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def countdown_timer(seconds, message):
    """Countdown timer with a custom message."""
    for remaining in range(seconds, 0, -1):
        minutes, seconds = divmod(remaining, 60)
        countdown = f"{minutes:02}:{seconds:02}"
        print(f"\r{message} : {countdown}", end="")
        time.sleep(1)
    print()

def process_bot(bot_manager: BotManager, bot) -> bool:
    """Process a single bot with optimized rate limit handling."""
    print(f"\n{'=' * 50}")
    print(f"Processing articles for bot: {bot.name}")
    print(f"Identity: {bot.identity[:50]}...")
    print(f"RSS URL: {bot.rss_url}")
    print('=' * 50)

    # Check global rate limit
    if bot_manager.is_bot_rate_limited(bot.name):
        print(f"⚠️ Bot {bot.name} is globally rate limited. Skipping...")
        return False

    # Use a cache file to track the last action
    cache_file = bot_manager.cache_dir / f"{bot.name}_last_action.txt"
    try:
        last_action = "article" if not cache_file.exists() else cache_file.read_text().strip()
    except Exception:
        last_action = "article"

    current_action = "mentions" if last_action == "article" else "article"
    success = False

    # Si l'action est article ou si on est rate limited sur get_users_tweets
    if current_action == "article" or bot_manager.is_rate_limited(bot.name, "get_users_tweets"):
        try:
            rss_feed = fetch_rss(bot.rss_url)
            if not rss_feed.empty:
                for _, article in rss_feed.iterrows():
                    if not bot_manager.db.is_title_tweeted(article['title']):
                        success = bot_manager.process_article(
                            bot=bot,
                            headline=article['title'],
                            description=article['description']
                        )
                        if success:
                            print(f"✅ New article posted for {bot.name}")
                            break
            if not success:
                print(f"No new articles to post for {bot.name}")
        except Exception as e:
            logger.error(f"Error processing article for {bot.name}: {e}")
    else:
        # Check for mentions
        try:
            client = bot_manager.get_api_client(bot)
            if not client:
                return False

            recent_tweets = bot_manager.execute_request(
                bot_name=bot.name,
                request_func=client.get_users_tweets,
                endpoint="get_users_tweets",
                id=bot.user_id,
                max_results=5
            )

            if recent_tweets and hasattr(recent_tweets, 'data') and recent_tweets.data:
                for tweet in recent_tweets.data:
                    if bot_manager.is_rate_limited(bot.name, "search_recent_tweets"):
                        break

                    replies = bot_manager.execute_request(
                        bot_name=bot.name,
                        request_func=client.search_recent_tweets,
                        endpoint="search_recent_tweets",
                        query=f"conversation_id:{tweet.id}",
                        max_results=10  # Minimum valeur acceptée par Twitter
                    )

                    if replies and hasattr(replies, 'data') and replies.data:
                        success = bot_manager.process_mentions(bot)
                        if success:
                            print(f"✅ Replies processed for {bot.name}")
                            break

            if not success:
                print(f"No replies to process for {bot.name}")
                # Si pas de mentions à traiter, on essaie de poster un article
                try:
                    rss_feed = fetch_rss(bot.rss_url)
                    if not rss_feed.empty:
                        for _, article in rss_feed.iterrows():
                            if not bot_manager.db.is_title_tweeted(article['title']):
                                success = bot_manager.process_article(
                                    bot=bot,
                                    headline=article['title'],
                                    description=article['description']
                                )
                                if success:
                                    print(f"✅ New article posted for {bot.name}")
                                    break
                except Exception as e:
                    logger.error(f"Error processing fallback article for {bot.name}: {e}")

        except Exception as e:
            logger.error(f"Error processing mentions for {bot.name}: {e}")

    # Save the current action for next time only if successful
    if success:
        try:
            cache_file.write_text(current_action)
        except Exception as e:
            logger.error(f"Error saving last action: {e}")

    return success

def main():
    print("🚀 Starting the program...")
    bot_manager = BotManager()
    
    while True:
        try:
            # Load active bots
            active_bots = bot_manager.db.get_active_bots()
            if not active_bots:
                print("\n❌ No active bots found.")
                countdown_timer(300, "⏳ Waiting before checking bots again")
                continue

            print(f"\n📊 Number of active bots found: {len(active_bots)}")
            
            processed_bots = set()
            success_count = 0

            # Process each active bot
            for bot in active_bots:
                if bot.name in processed_bots:
                    continue

                success = process_bot(bot_manager, bot)
                processed_bots.add(bot.name)

                if success:
                    success_count += 1
                    time.sleep(random.uniform(3, 7))  # Small delay between bots
                else:
                    time.sleep(2)

            # Handle subsequent cycles
            if all(bot_manager.is_rate_limited(bot.name, "get_users_tweets") for bot in active_bots):
                wait_time = min(
                    max(0, bot_manager.rate_limited[bot.name] - time.time())
                    for bot in active_bots if bot_manager.is_rate_limited(bot.name)
                )
                print(f"\n⚠️ All bots are rate limited. Resuming in {wait_time:.0f} seconds.")
                countdown_timer(wait_time, "⏳ Waiting for rate limits to reset")
                bot_manager.clean_expired_limits()
            elif success_count > 0:
                countdown_timer(1800, "⏳ Short wait before the next cycle")
            else:
                countdown_timer(1800, "⏳ Medium wait before the next cycle")

        except KeyboardInterrupt:
            print("\n👋 User requested stop.")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            countdown_timer(15, "⏳ Waiting after error")

    print("✨ Program finished.")

if __name__ == "__main__":
    main()