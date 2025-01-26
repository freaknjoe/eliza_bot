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
from datetime import datetime
from openai import OpenAI

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CryptoSocialBot")

# Flask setup for Render port binding
app = Flask(__name__)

@app.route('/')
def home():
    return "Crypto, Memes, AI, DeFi, and DeFiAI Social Bot is running!"

def start_flask():
    port = int(os.environ.get("PORT", 10000))  # Default to 10000 if PORT is not set
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
    raise ValueError("API credentials are not properly set as environment variables.")

# Authenticate with Twitter API v2
client = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET_KEY,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# Initialize OpenAI and DeepSeek clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")

# Path to the images folder
IMAGES_FOLDER = "images"  # Ensure this folder exists and contains your images
MEMORY_FILE = "bot_memory.json"  # File to store prompts and responses

# Ensure the images folder exists
if not os.path.exists(IMAGES_FOLDER):
    logger.error(f"Images folder '{IMAGES_FOLDER}' not found.")
    raise FileNotFoundError(f"Images folder '{IMAGES_FOLDER}' not found.")

# Ensure the memory file exists
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump({"prompts": [], "responses": []}, f)

# Rate limit tracking
RATE_LIMIT_WINDOW = 900  # 15 minutes in seconds
MAX_TWEETS_PER_WINDOW = 900
tweet_count = 0
last_reset_time = time.time()

def check_rate_limit():
    global tweet_count, last_reset_time
    current_time = time.time()
    if current_time - last_reset_time >= RATE_LIMIT_WINDOW:
        tweet_count = 0
        last_reset_time = current_time
    if tweet_count >= MAX_TWEETS_PER_WINDOW:
        sleep_time = RATE_LIMIT_WINDOW - (current_time - last_reset_time)
        logger.warning(f"Rate limit reached. Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)
        tweet_count = 0
        last_reset_time = time.time()

# Fetch trending crypto topics from CryptoPanic
def fetch_trending_topics():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}"
        response = requests.get(url)
        if response.status_code == 200 and "results" in response.json():
            news_items = response.json()["results"]
            return [item["title"] for item in news_items if "title" in item][:5]
        else:
            logger.warning(f"Failed to fetch trending topics: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
        return []

# Memory system
def load_memory():
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f)

def update_memory(prompt, response):
    memory = load_memory()
    memory["prompts"].append(prompt)
    memory["responses"].append(response)
    save_memory(memory)

# Exponential backoff for OpenAI requests
def call_openai_with_backoff(prompt):
    retries = 0
    while retries < 5:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a witty assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content.strip()
        except openai.error.RateLimitError:
            retries += 1
            time.sleep(min(2 ** retries, 60))
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}")
            return None

# Fetch reasoning content from DeepSeek
def fetch_deepseek_response(user_prompt):
    try:
        deepseek_response = deepseek_client.chat.completions.create(
            model='deepseek-chat',
            messages=[{"role": "user", "content": user_prompt}]
        )
        return deepseek_response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error fetching DeepSeek response: {e}")
        return None

# Reply to mentions
def reply_to_mentions():
    try:
        mentions = client.get_users_mentions(user_id="1878624202229493760", max_results=5)
        if mentions.data:
            for mention in mentions.data:
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

# Main bot logic
def run_bot():
    while True:
        action = random.choice(["regular_tweet", "meme_tweet", "interact"])
        
        if action == "regular_tweet":
            prompt = "Create a witty tweet about crypto, AI, or DeFi."
            tweet = call_openai_with_backoff(prompt)
            if tweet:
                check_rate_limit()
                client.create_tweet(text=tweet)
                logger.info(f"Posted tweet: {tweet}")

        elif action == "meme_tweet":
            trending_topics = fetch_trending_topics()
            if trending_topics:
                meme_caption = call_openai_with_backoff(f"Create a witty crypto meme caption about: {', '.join(trending_topics)}")
                if meme_caption:
                    # Add meme generation logic here if needed
                    logger.info(f"Generated meme caption: {meme_caption}")

        elif action == "interact":
            reply_to_mentions()

        logger.info("Sleeping for 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()
