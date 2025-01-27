import os
import random
import json
import logging
import openai
import time
import threading
import requests
from flask import Flask
import tweepy
from PIL import Image, ImageDraw, ImageFont

# Logging setup
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logging
logger = logging.getLogger("CryptoSocialBot")

# Flask setup for Render port binding
app = Flask(__name__)

@app.route('/')
def home():
    logger.debug("Received request to home endpoint.")
    return "Crypto, Memes, AI, DeFi, and DeFiAI Social Bot is running!"

def start_flask():
    port = int(os.environ.get("PORT", 10000))  # Default to 10000 if PORT is not set
    logger.debug(f"Starting Flask app on port {port}.")
    app.run(host='0.0.0.0', port=port)

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
RATE_LIMIT_WINDOW = 900  # 15 minutes
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
    if time.time() - last_trending_time < 900:  # 15 minutes
        logger.debug("Returning cached trending topics.")
        return cached_trending_topics
    try:
        logger.debug("Fetching trending topics from CryptoPanic.")
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}"
        response = requests.get(url)
        if response.status_code == 200 and "results" in response.json():
            cached_trending_topics = [item["title"] for item in response.json()["results"] if "title" in item][:5]
            last_trending_time = time.time()
            return cached_trending_topics
    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
    return []

def load_memory():
    """Load past prompts and responses."""
    logger.debug("Loading memory from file.")
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(memory):
    """Save prompts and responses."""
    logger.debug("Saving memory to file.")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f)

def update_memory(prompt, response):
    """Update memory with a new prompt and response."""
    logger.debug("Updating memory with a new prompt and response.")
    memory = load_memory()
    memory["prompts"].append(prompt)
    memory["responses"].append(response)
    save_memory(memory)

def fetch_deepseek_response(user_prompt):
    """Fetch reasoning content from DeepSeek."""
    logger.debug(f"Fetching DeepSeek response for prompt: {user_prompt}")
    try:
        response = openai.ChatCompletion.create(
            model='deepseek-chat',
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error fetching DeepSeek response: {e}")
        return None

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
            return response.choices[0].message.content.strip()
        except openai.error.RateLimitError:
            retries += 1
            logger.warning(f"Rate limit error. Retrying... Attempt {retries}")
            time.sleep(min(2 ** retries, 60))
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}")
            return None

def reply_to_mentions():
    """Reply to mentions on Twitter."""
    logger.debug("Checking for mentions to reply to.")
    try:
        mentions = client.get_users_mentions(user_id="1878624202229493760", max_results=5)
        if mentions.data:
            for mention in mentions.data:
                logger.debug(f"Processing mention: {mention.text}")
                if not mention.favorited:
                    user_prompt = mention.text.replace("@3DPUNKBOT", "").strip()
                    reasoning_content = fetch_deepseek_response(user_prompt)
                    
                    if reasoning_content is None:
                        logger.info(f"Skipping reply to @{mention.author.username} due to DeepSeek failure.")
                        continue
                    
                    final_response = call_openai_with_backoff(f"Based on this reasoning: {reasoning_content}, respond to this: {user_prompt}")
                    if final_response:
                        client.create_tweet(
                            text=f"@{mention.author.username} {final_response}",
                            in_reply_to_tweet_id=mention.id
                        )
                        client.like(mention.id)
                        logger.info(f"Replied to @{mention.author.username}.")
    except Exception as e:
        logger.error(f"Error replying to mentions: {e}")

def run_bot():
    """Main bot loop."""
    logger.debug("Starting the bot.")
    while True:
        action = random.choice(["regular_tweet", "meme_tweet", "interact"])
        
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
                    logger.info(f"Generated meme caption: {meme_caption}")

        elif action == "interact":
            logger.debug("Interacting with mentions.")
            reply_to_mentions()

        logger.debug("Bot is sleeping for 15 minutes.")
        time.sleep(900)

if __name__ == "__main__":
    logger.debug("Initializing the bot.")
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()
