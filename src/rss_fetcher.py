#src/rss_fetcher.py

import feedparser
import pandas as pd
import ssl
import random

def fetch_rss(rss_url):
    """
    Fetches articles from the RSS feed.
    The rss_url parameter can now contain multiple URLs separated by commas.
    Handles cases where the description is missing.
    """
    ssl._create_default_https_context = ssl._create_unverified_context
    
    try:
        # Split URLs and clean up spaces
        rss_urls = [url.strip() for url in rss_url.split(',') if url.strip()]
        
        # Check if the list of URLs is not empty
        if not rss_urls:
            print("No valid RSS URLs found")
            return pd.DataFrame()
        
        # Select a random URL
        selected_url = random.choice(rss_urls)
        print(f"Selected RSS feed: {selected_url}")
        
        # Parse the selected RSS feed
        feed = feedparser.parse(selected_url)
        
        entries = [{
            'title': getattr(entry, 'title', ''),
            'description': getattr(entry, 'description', ''),  # Returns '' if no description
            'link': getattr(entry, 'link', '')
        } for entry in feed.entries]
        
        return pd.DataFrame(entries)
        
    except Exception as e:
        print(f"Error fetching the RSS feed: {e}")
        return pd.DataFrame()