import os
import random
import json
import logging
import time
import threading
import requests
from flask import Flask
import tweepy
from PIL import Image, ImageDraw, ImageFont
import openai  

# Logging setup
logging.basicConfig(level=logging.DEBUG)  
logger = logging.getLogger("CryptoSocialBot")

# Flask setup for Render port binding
app = Flask(__name__)

@app.route('/')
def home():
    logger.debug("Received request to home endpoint.")
    return "Crypto, Memes, AI, DeFi, and DeFiAI Social Bot is running!"

def start_flask():
    port = int(os.getenv("PORT", 10000))  
    app.run(host="0.0.0.0", port=port)

# Fetch credentials from environment variables
API_KEY = os.getenv('TWITTER_API_KEY')
API_SECRET_KEY = os.getenv('TWITTER_API_SECRET_KEY')
ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CRYPTOPANIC_API_KEY = os.getenv('CRYPTOPANIC_API_KEY')

# Validate API credentials
if not all([API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, DEEPSEEK_API_KEY, OPENAI_API_KEY, CRYPTOPANIC_API_KEY]):
    logger.critical("API credentials are not properly set as environment variables.")
    raise ValueError("API credentials are missing.")

# Authenticate with Twitter API v2
client = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET_KEY,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

# Paths and constants
IMAGES_FOLDER = "images"
MEMORY_FILE = "bot_memory.json"

# Rate limit tracking
RATE_LIMIT_WINDOW = 900  
MAX_TWEETS_PER_WINDOW = 20
tweet_count = 0
last_reset_time = time.time()

# Caching for trending topics
last_trending_time = 0
cached_trending_topics = []

# Ensure the images folder exists
if not os.path.exists(IMAGES_FOLDER):
    logger.error(f"Images folder '{IMAGES_FOLDER}' not found.")
    raise FileNotFoundError(f"Images folder '{IMAGES_FOLDER}' not found.")

# Ensure the memory file exists
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump({"prompts": [], "responses": []}, f)

def check_rate_limit():
    """Ensure we're within rate limits."""
    global tweet_count, last_reset_time
    current_time = time.time()
    logger.debug(f"Current tweet count: {tweet_count}, Current time: {current_time}")
    if current_time - last_reset_time >= RATE_LIMIT_WINDOW:
        logger.debug("Resetting rate limits.")
        tweet_count = 0
        last_reset_time = current_time
    if tweet_count >= MAX_TWEETS_PER_WINDOW:
        sleep_time = RATE_LIMIT_WINDOW - (current_time - last_reset_time)
        logger.warning(f"Rate limit reached. Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)
        tweet_count = 0
        last_reset_time = time.time()

def fetch_trending_topics():
    """Fetch trending crypto topics from CryptoPanic with caching."""
    global last_trending_time, cached_trending_topics
    if time.time() - last_trending_time < 900:  
        logger.debug("Returning cached trending topics.")
        return cached_trending_topics
    try:
        logger.debug("Fetching trending topics from CryptoPanic.")
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        if "results" in response.json():
            cached_trending_topics = [item["title"] for item in response.json()["results"] if "title" in item][:5]
            last_trending_time = time.time()
            logger.debug(f"Trending topics fetched: {cached_trending_topics}")
            return cached_trending_topics
    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
    return []

def call_openai_with_backoff(prompt):
    """Fetch a witty response with OpenAI and exponential backoff."""
    logger.debug(f"Fetching response from OpenAI for prompt: {prompt}")
    retries = 0
    while retries < 5:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a witty assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200
            )
            logger.debug(f"OpenAI response: {response}")
            return response.choices[0].message.content.strip()
        except openai.error.RateLimitError:
            retries += 1
            logger.warning(f"Rate limit error. Retrying... Attempt {retries}")
            time.sleep(min(2 ** retries, 60))
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}")
            return None

def generate_meme(caption):
    """Generate a meme image with a caption."""
    try:
        image = Image.open(os.path.join(IMAGES_FOLDER, "meme_template.jpg"))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.text((10, 10), caption, font=font, fill="white")
        meme_path = os.path.join(IMAGES_FOLDER, "generated_meme.jpg")
        image.save(meme_path)
        return meme_path
    except Exception as e:
        logger.error(f"Error generating meme: {e}")
        return None

def post_meme(caption):
    """Generate and post a meme."""
    meme_path = generate_meme(caption)
    if meme_path:
        media = client.media_upload(meme_path)
        client.create_tweet(text=caption, media_ids=[media.media_id])
        logger.info(f"Posted meme: {caption}")

def run_bot():
    """Main bot loop."""
    logger.debug("Starting the bot.")
    while True:
        action = random.choice(["regular_tweet", "meme_tweet", "analyze_trends"])
        logger.debug(f"Selected action: {action}")  # Log selected action
        
        if action == "regular_tweet":
            logger.debug("Posting a regular tweet.")
            prompt = "Create a witty tweet about crypto, AI, or DeFi."
            tweet = call_openai_with_backoff(prompt)
            if tweet:
                check_rate_limit()
                client.create_tweet(text=tweet)
                logger.info(f"Posted tweet: {tweet}")
        
        elif action == "meme_tweet":
            logger.debug("Generating a meme tweet.")
            trending_topics = fetch_trending_topics()
            if trending_topics:
                meme_caption = call_openai_with_backoff(f"Create a witty crypto meme caption about: {', '.join(trending_topics)}")
                if meme_caption:
                    post_meme(meme_caption)

        elif action == "analyze_trends":
            logger.debug("Analyzing trends using DeepSeek.")
            prompt = "Analyze the latest trends in crypto and provide a summary."
            analysis = fetch_deepseek_response(prompt)
            if analysis:
                tweet = f"📊 Crypto Trend Analysis:\n\n{analysis}"
                check_rate_limit()
                client.create_tweet(text=tweet)
                logger.info(f"Posted analysis: {tweet}")

        sleep_time = random.randint(2 * 3600, 3 * 3600)  # Sleep for 2-3 hours
        logger.debug(f"Bot is sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)  # Sleep for the calculated interval

if __name__ == "__main__":
    logger.debug("Initializing the bot.")
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()
