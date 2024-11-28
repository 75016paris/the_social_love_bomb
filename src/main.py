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
    """Process a single bot."""
    print(f"\n{'=' * 50}")
    print(f"Processing articles for bot: {bot.name}")
    print(f"Identity: {bot.identity[:50]}...")
    print(f"RSS URL: {bot.rss_url}")
    print('=' * 50)

    # Check global rate limit
    if bot_manager.is_bot_rate_limited(bot.name):
        print(f"⚠️ Bot {bot.name} is globally rate limited. Skipping...")
        return False

    # Check endpoint-specific rate limit
    if bot_manager.is_rate_limited(bot.name, "process_articles"):
        print(f"⚠️ Bot {bot.name} is rate limited for processing articles. Skipping...")
        return False

    # Step 1: Handle mentions or replies
    try:
        mentions_result = bot_manager.process_mentions(bot)
        if mentions_result:
            print(f"✅ Mentions or replies processed for {bot.name}")
            return True
        elif mentions_result == 'PROCESS_ARTICLE':
            # Continue to process_article
            pass
    except Exception as e:
        logger.error(f"Error processing mentions for bot {bot.name}: {e}", exc_info=True)

    # Step 2: Process articles only if no mentions were handled
    try:
        rss_feed = fetch_rss(bot.rss_url)
        if rss_feed.empty:
            print(f"No articles found for {bot.name}")
            return False

        # Iterate through RSS articles
        for _, article in rss_feed.iterrows():
            if bot_manager.db.is_title_tweeted(article['title']):
                print(f"Article already processed: {article['title'][:50]}...")
                continue

            success = bot_manager.process_article(
                bot=bot,
                headline=article['title'],
                description=article['description']
            )

            if success:
                print(f"✅ Tweet successfully posted for {bot.name}")
                return True
            else:
                print(f"❌ Failed to post tweet for {bot.name}: {article['title'][:50]}...")

    except tweepy.errors.TooManyRequests as e:
        reset_time = int(time.time() + 900)  # Default value
        if hasattr(e, 'response') and hasattr(e.response, 'headers'):
            reset_time = int(e.response.headers.get('x-rate-limit-reset', reset_time))
        bot_manager.mark_rate_limited(bot.name, "process_articles", reset_time)
        print(f"⚠️ Bot {bot.name} rate limited. Will retry after reset.")
    except Exception as e:
        logger.error(f"Error processing bot {bot.name}: {e}", exc_info=True)

    return False

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