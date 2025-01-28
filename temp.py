import os
import random
import time
import logging
import requests
from requests_oauthlib import OAuth1
from flask import Flask
import tweepy
from datetime import datetime
from PIL import Image
import threading
import re

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("CryptoSocialBot")

# Flask setup
app = Flask(__name__)

@app.route('/')
def home():
    return "CryptoSocialBot is running!"

def start_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Fetch credentials from environment variables
API_KEY = os.getenv('TWITTER_API_KEY')
API_SECRET_KEY = os.getenv('TWITTER_API_SECRET_KEY')
ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
CRYPTOPANIC_API_KEY = os.getenv('CRYPTOPANIC_API_KEY')

# Constants for $FEDJA
FEDJA_CONTRACT_ADDRESS = "9oDw3Q36a8mVHfPCSmxYBXE9iLeJjsCYu97JGpPwDvVZ"
FEDJA_TWITTER = "https://x.com/Fedja_SOL"
IMAGES_FOLDER = "images"  # Folder containing images for posts

# Validate API credentials
if not all([API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, DEEPSEEK_API_KEY, CRYPTOPANIC_API_KEY]):
    logger.critical("API credentials are not properly set as environment variables.")
    raise ValueError("API credentials are missing.")

# Authenticate with Twitter API v1.1 (for media upload)
auth_v1 = tweepy.OAuth1UserHandler(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET_KEY,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)
api_v1 = tweepy.API(auth_v1)

# Authenticate with Twitter API v2 (for posting tweets)
client_v2 = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET_KEY,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# Rate limiting for DeepSeek
DEEPSEEK_RATE_LIMIT = {
    "last_request_time": 0,
    "retry_after": 1,  # Default retry delay in seconds
}

# Fallback prompts categorized by type
FALLBACK_PROMPTS = {
    "crypto_meme": [
        "What's the most interesting crypto meme you've seen this week? Describe it briefly.",
        "Crypto memes are the best! What's your favorite and why?",
        "The crypto community loves memes. What's the funniest one you've seen recently?",
        "Memes are taking over crypto Twitter. What's your take on it?",
        "What's the latest crypto meme trend? Let's discuss!",
    ],
    "defi_update": [
        "What's the latest development in DeFi? Let's talk about it!",
        "DeFi is changing finance. What's your favorite platform and why?",
        "What's the most exciting DeFi project right now?",
        "DeFi is the future. What's your favorite DeFi platform?",
        "What's new in the world of decentralized finance?",
    ],
    "ai_development": [
        "AI is revolutionizing crypto. What's the most exciting development?",
        "What's the impact of AI on the crypto market?",
        "AI and crypto are a powerful combo. What's your favorite application?",
        "How is AI changing the crypto landscape?",
        "What's the latest AI tool in crypto you can't live without?",
    ],
    "general_crypto": [
        "What's your favorite cryptocurrency and why?",
        "What's the most interesting thing about crypto today?",
        "What's your take on the current crypto market?",
        "What's the best thing about crypto?",
        "What's the most surprising thing about crypto in 2023?",
    ],
}

def get_dynamic_prompt(base_prompt):
    """Insert the current year into the base prompt."""
    current_year = datetime.now().year
    return base_prompt.replace("{year}", str(current_year))

def fetch_cryptopanic_topics():
    """Fetch trending topics from CryptoPanic filtered for relevant categories."""
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()  # Raise error if the request failed

        # Extract relevant topics
        results = response.json().get("results", [])
        relevant_topics = [
            item["title"] for item in results if any(
                keyword in item["title"].lower() for keyword in ["memecoin", "defi", "ai", "defiai", "btc", "eth", "solana"]
            )
        ]
        return relevant_topics[:5]  # Limit to the top 5 topics
    except Exception as e:
        logger.error(f"Error fetching topics from CryptoPanic: {e}")
        return []

def call_deepseek(prompt, model="deepseek-chat"):
    """Fetch a response from DeepSeek API with rate limiting."""
    global DEEPSEEK_RATE_LIMIT
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    # Ensure we respect the retry-after delay
    current_time = time.time()
    if current_time - DEEPSEEK_RATE_LIMIT["last_request_time"] < DEEPSEEK_RATE_LIMIT["retry_after"]:
        sleep_time = DEEPSEEK_RATE_LIMIT["retry_after"] - (current_time - DEEPSEEK_RATE_LIMIT["last_request_time"])
        logger.warning(f"DeepSeek rate limit: Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()  # Raise an error for bad responses

        # Update rate limit tracking
        DEEPSEEK_RATE_LIMIT["last_request_time"] = time.time()

        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"Error calling DeepSeek API: {e}")
        return None

def summarize_text(text):
    """Summarize the given text into a concise version using DeepSeek, ensuring it's 280 characters or less."""
    prompt = f"Summarize the following text into a concise paragraph of 280 characters or less: {text}"
    summarized_text = call_deepseek(prompt, model="deepseek-chat")
    
    # If summarization fails or exceeds character limit, return None
    if not summarized_text or len(summarized_text) > 280:
        logger.warning("Summarization failed or exceeded character limit.")
        return None
    
    return summarized_text

def select_random_image():
    """Select a random image from the images folder."""
    try:
        images = [os.path.join(IMAGES_FOLDER, img) for img in os.listdir(IMAGES_FOLDER) if img.endswith(('.png', '.jpg', '.jpeg'))]
        if not images:
            logger.warning("No images found in the images folder.")
            return None
        return random.choice(images)
    except Exception as e:
        logger.error(f"Error selecting random image: {e}")
        return None

def generate_and_post_tweet(base_prompt, category="general_crypto"):
    """Generate a detailed text, summarize it to 280 characters or less, and post as a tweet."""
    try:
        # Generate detailed text
        detailed_text = call_deepseek(base_prompt)
        if not detailed_text:
            logger.warning("Failed to generate detailed text. Using fallback.")
            detailed_text = random.choice(FALLBACK_PROMPTS[category])
        
        # Summarize the detailed text to 280 characters or less
        summarized_text = summarize_text(detailed_text)
        if not summarized_text:
            logger.warning("Summarization failed. Using fallback prompt.")
            final_tweet = random.choice(FALLBACK_PROMPTS[category])
        else:
            final_tweet = summarized_text

        # Ensure the final tweet is 280 characters or less
        if len(final_tweet) > 280:
            logger.warning("Final tweet exceeds 280 characters. Using fallback.")
            final_tweet = random.choice(FALLBACK_PROMPTS[category])

        # If the final tweet is still too long, use a short fallback
        if len(final_tweet) > 280:
            final_tweet = random.choice([
                "Crypto is wild today! 🚀",
                "AI is changing everything! 🤖",
                "DeFi is the future! 📈",
                "Memecoins are here to stay! 🐕",
            ])
            logger.warning("Using short fallback tweet.")

        logger.info(f"Final tweet: {final_tweet}")
        
        # Select a random image
        image_path = select_random_image()

        # If an image is found, append $FEDJA reference
        if image_path:
            # Randomly choose between including the contract address or Twitter link
            reference_type = random.choice(["contract", "twitter"])
            
            if reference_type == "contract":
                fedja_reference = f"\n\n$FEDJA | {FEDJA_CONTRACT_ADDRESS} 🐕 #FEDJA"
            else:
                fedja_reference = f"\n\n$FEDJA | {FEDJA_TWITTER} 🐕 #FEDJA"
            
            # Ensure the final tweet does not exceed 280 characters
            if len(final_tweet) + len(fedja_reference) <= 280:
                final_tweet += fedja_reference
                logger.info(f"Updated tweet with $FEDJA reference: {final_tweet}")
            else:
                # If the reference cannot be added without exceeding the limit, prioritize the reference
                max_length = 280 - len(fedja_reference)
                final_tweet = final_tweet[:max_length] + fedja_reference
                logger.info(f"Adjusted tweet to include $FEDJA reference: {final_tweet}")

        # Post the tweet
        post_tweet(final_tweet, image_path)

    except Exception as e:
        logger.error(f"Error in generate_and_post_tweet: {e}")
        return None

def post_tweet(text, image_path=None):
    """Post a tweet with error handling."""
    try:
        logger.info(f"Attempting to post tweet: {text}")
        if image_path:
            # Upload media using Twitter API v1.1
            media = api_v1.media_upload(filename=image_path)
            # Post tweet with media using Twitter API v2
            response = client_v2.create_tweet(text=text, media_ids=[media.media_id])
        else:
            # Post text-only tweet using Twitter API v2
            response = client_v2.create_tweet(text=text)
        
        # Access the tweet ID from the response dictionary
        if response and response.data:
            tweet_id = response.data['id']
            logger.info(f"Tweet posted successfully! Tweet ID: {tweet_id}")
            return tweet_id
        else:
            logger.error("Invalid response from Twitter API. No tweet data found.")
            return None
    except tweepy.TweepyException as e:
        logger.error(f"Error posting tweet: {e}")
        return None

def post_fedja_tweet():
    """Post a bullish tweet about $FEDJA."""
    base_prompt = f"Create a detailed paragraph about $FEDJA, a memecoin on Solana. Discuss its potential, community, and recent developments."
    generate_and_post_tweet(base_prompt, category="crypto_meme")

def post_regular_tweet():
    """Post a regular tweet about crypto, AI, or DeFi."""
    base_prompt = f"Create a detailed paragraph about the current state of crypto, AI, or DeFi in {datetime.now().year}. Discuss key trends and developments."
    generate_and_post_tweet(base_prompt, category="general_crypto")

def post_meme_tweet():
    """Post a crypto meme tweet."""
    base_prompt = f"Create a detailed paragraph about a funny or interesting crypto meme or situation in {datetime.now().year}."
    generate_and_post_tweet(base_prompt, category="crypto_meme")

def run_bot():
    """Main bot loop."""
    logger.info("Starting the bot.")
    while True:
        # Randomly select action with 20% chance for $FEDJA posts
        if random.random() < 0.2:
            action = "fedja_tweet"
        else:
            action = random.choice(["regular_tweet", "meme_tweet"])
        
        logger.info(f"Selected action: {action}")

        if action == "fedja_tweet":
            post_fedja_tweet()
            time.sleep(43200)  # Post about $FEDJA every 12 hours

        elif action == "regular_tweet":
            post_regular_tweet()
            time.sleep(1800)  # Sleep for 30 minutes

        elif action == "meme_tweet":
            post_meme_tweet()
            time.sleep(3600)  # Sleep for 1 hour

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()