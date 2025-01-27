import os
import random
import time
import threading
import requests
import logging
from flask import Flask
import tweepy
from datetime import datetime
from PIL import Image  # For verifying images

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

# Authenticate with Twitter
client = tweepy.Client(
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

def call_deepseek(prompt):
    """Fetch a response from DeepSeek API with rate limiting."""
    global DEEPSEEK_RATE_LIMIT
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
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

def post_tweet(text, image_path=None):
    """Post a tweet with error handling."""
    try:
        if image_path:
            media = client.media_upload(filename=image_path)
            client.create_tweet(text=text, media_ids=[media.media_id])
        else:
            client.create_tweet(text=text)
        logger.info(f"Posted tweet: {text}")
    except tweepy.TweepyException as e:
        logger.error(f"Error posting tweet: {e}")

def post_fedja_tweet():
    """Post a bullish tweet about $FEDJA."""
    base_prompt = f"Create a bullish tweet about $FEDJA, a memecoin on Solana. Mention the contract address {FEDJA_CONTRACT_ADDRESS} or the Twitter account {FEDJA_TWITTER}. Keep it exciting and engaging."
    tweet = call_deepseek(base_prompt)
    if not tweet:
        tweet = f"🚀 $FEDJA is taking the Solana memecoin world by storm! 🌕 Check out the contract: {FEDJA_CONTRACT_ADDRESS} or follow us here: {FEDJA_TWITTER}. #Solana #Memecoin"

    image_path = select_random_image()
    post_tweet(tweet, image_path)

def run_bot():
    """Main bot loop."""
    logger.info("Starting the bot.")
    while True:
        action = random.choice(["regular_tweet", "meme_tweet", "fedja_tweet"])
        logger.info(f"Selected action: {action}")

        if action == "fedja_tweet":
            post_fedja_tweet()
            time.sleep(43200)  # Post about $FEDJA every 12 hours

        elif action == "regular_tweet":
            base_prompt = f"Create a witty tweet about crypto, AI, or DeFi in {datetime.now().year}."
            trending_topics = fetch_cryptopanic_topics()
            if trending_topics:
                base_prompt += f" Reference trending topics: {', '.join(trending_topics)}."
            tweet = call_deepseek(base_prompt)
            if tweet:
                post_tweet(tweet)
                time.sleep(1800)  # Sleep for 30 minutes
            else:
                logger.warning("Failed to generate tweet. Using fallback.")
                fallback_tweet = get_dynamic_prompt("🚀 Crypto, AI, and DeFi are the future! {year} is wild. #Crypto #AI #DeFi")
                post_tweet(fallback_tweet)
                time.sleep(1800)

        elif action == "meme_tweet":
            base_prompt = f"Create a witty crypto meme caption for {datetime.now().year}."
            trending_topics = fetch_cryptopanic_topics()
            if trending_topics:
                base_prompt += f" Incorporate these trending topics: {', '.join(trending_topics)}."
            meme_caption = call_deepseek(base_prompt)
            if meme_caption:
                post_tweet(meme_caption)
                time.sleep(3600)  # Sleep for 1 hour
            else:
                logger.warning("Failed to generate meme caption. Using fallback.")
                fallback_caption = get_dynamic_prompt("🤖 Just another day in the world of crypto and AI in {year}! #CryptoMeme #AI")
                post_tweet(fallback_caption)
                time.sleep(3600)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()
