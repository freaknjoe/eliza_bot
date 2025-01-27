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

# Rate limit tracking for Twitter
TWITTER_RATE_LIMITS = {
    "tweets": {"daily_limit": 50, "remaining": 50, "reset_time": 0},
    "requests": {"window": 900, "limit": 500, "remaining": 500, "reset_time": time.time()},
}

# Rate limit tracking for OpenAI
OPENAI_RATE_LIMITS = {
    "gpt-3.5-turbo": {"tpm": 40000, "rpm": 3, "tokens_used": 0, "requests_used": 0, "last_reset": time.time()},
    "gpt-4o-mini": {"tpm": 60000, "rpm": 3, "tokens_used": 0, "requests_used": 0, "last_reset": time.time()},
}

# Rate limit tracking for DeepSeek
DEEPSEEK_RATE_LIMIT = {
    "last_request_time": 0,
    "retry_after": 1,  # Default retry delay in seconds
}

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

def check_twitter_rate_limit():
    """Ensure we're within Twitter rate limits."""
    global TWITTER_RATE_LIMITS
    current_time = time.time()

    # Check daily tweet limit
    if current_time >= TWITTER_RATE_LIMITS["tweets"]["reset_time"]:
        TWITTER_RATE_LIMITS["tweets"]["remaining"] = TWITTER_RATE_LIMITS["tweets"]["daily_limit"]
        TWITTER_RATE_LIMITS["tweets"]["reset_time"] = current_time + 86400  # Reset after 24 hours

    if TWITTER_RATE_LIMITS["tweets"]["remaining"] <= 0:
        sleep_time = TWITTER_RATE_LIMITS["tweets"]["reset_time"] - current_time
        logger.warning(f"Daily tweet limit reached. Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)
        TWITTER_RATE_LIMITS["tweets"]["remaining"] = TWITTER_RATE_LIMITS["tweets"]["daily_limit"]
        TWITTER_RATE_LIMITS["tweets"]["reset_time"] = time.time() + 86400

    # Check request rate limit
    if current_time - TWITTER_RATE_LIMITS["requests"]["reset_time"] >= TWITTER_RATE_LIMITS["requests"]["window"]:
        TWITTER_RATE_LIMITS["requests"]["remaining"] = TWITTER_RATE_LIMITS["requests"]["limit"]
        TWITTER_RATE_LIMITS["requests"]["reset_time"] = current_time

    if TWITTER_RATE_LIMITS["requests"]["remaining"] <= 0:
        sleep_time = TWITTER_RATE_LIMITS["requests"]["window"] - (current_time - TWITTER_RATE_LIMITS["requests"]["reset_time"])
        logger.warning(f"Twitter request limit reached. Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)
        TWITTER_RATE_LIMITS["requests"]["remaining"] = TWITTER_RATE_LIMITS["requests"]["limit"]
        TWITTER_RATE_LIMITS["requests"]["reset_time"] = time.time()

def check_openai_rate_limit(model):
    """Ensure we're within OpenAI rate limits for the specified model."""
    global OPENAI_RATE_LIMITS
    current_time = time.time()
    usage = OPENAI_RATE_LIMITS[model]

    # Reset counters if a minute has passed
    if current_time - usage["last_reset"] >= 60:
        usage["tokens_used"] = 0
        usage["requests_used"] = 0
        usage["last_reset"] = current_time

    # Check token limit
    if usage["tokens_used"] >= usage["tpm"]:
        sleep_time = 60 - (current_time - usage["last_reset"])
        logger.warning(f"OpenAI {model} token limit reached. Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)
        usage["tokens_used"] = 0
        usage["requests_used"] = 0
        usage["last_reset"] = time.time()

    # Check request limit
    if usage["requests_used"] >= usage["rpm"]:
        sleep_time = 60 - (current_time - usage["last_reset"])
        logger.warning(f"OpenAI {model} request limit reached. Sleeping for {sleep_time} seconds.")
        time.sleep(sleep_time)
        usage["tokens_used"] = 0
        usage["requests_used"] = 0
        usage["last_reset"] = time.time()

def fetch_deepseek_response(prompt):
    """Fetch a response from DeepSeek with dynamic rate limiting."""
    global DEEPSEEK_RATE_LIMIT
    url = "https://api.deepseek.com/v1/chat/completions"  # Example DeepSeek API endpoint
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
        response.raise_for_status()

        # Update rate limit tracking
        DEEPSEEK_RATE_LIMIT["last_request_time"] = time.time()

        # Check for rate limit headers
        if "X-RateLimit-Remaining" in response.headers and "X-RateLimit-Reset" in response.headers:
            remaining_requests = int(response.headers["X-RateLimit-Remaining"])
            reset_time = int(response.headers["X-RateLimit-Reset"])
            if remaining_requests == 0:
                DEEPSEEK_RATE_LIMIT["retry_after"] = reset_time - time.time()
                logger.warning(f"DeepSeek rate limit reached. Retry after {DEEPSEEK_RATE_LIMIT['retry_after']} seconds.")
            else:
                DEEPSEEK_RATE_LIMIT["retry_after"] = max(1, reset_time / remaining_requests)

        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:  # Rate limit exceeded
            retry_after = int(e.response.headers.get("Retry-After", 1))
            DEEPSEEK_RATE_LIMIT["retry_after"] = retry_after
            logger.warning(f"DeepSeek rate limit exceeded. Retry after {retry_after} seconds.")
            time.sleep(retry_after)
            return fetch_deepseek_response(prompt)  # Retry the request
        else:
            logger.error(f"DeepSeek API error: {e}")
            return None
    except Exception as e:
        logger.error(f"Error calling DeepSeek API: {e}")
        return None

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

def call_openai_with_backoff(prompt, model="gpt-3.5-turbo"):
    """Fetch a witty response with OpenAI and exponential backoff."""
    logger.debug(f"Fetching response from OpenAI for prompt: {prompt}")
    retries = 0
    while retries < 5:
        try:
            # Check OpenAI rate limits
            check_openai_rate_limit(model)

            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a witty assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200
            )
            logger.debug(f"OpenAI response: {response}")

            # Update usage counters
            OPENAI_RATE_LIMITS[model]["tokens_used"] += response["usage"]["total_tokens"]
            OPENAI_RATE_LIMITS[model]["requests_used"] += 1

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
        # Randomly choose an action
        action = random.choice(["regular_tweet", "meme_tweet", "analyze_trends"])
        logger.debug(f"Selected action: {action}")

        if action == "regular_tweet":
            logger.debug("Posting a regular tweet.")
            prompt = "Create a witty tweet about crypto, AI, or DeFi."
            tweet = call_openai_with_backoff(prompt, model="gpt-3.5-turbo")
            if tweet:
                check_twitter_rate_limit()
                client.create_tweet(text=tweet)
                TWITTER_RATE_LIMITS["tweets"]["remaining"] -= 1
                logger.info(f"Posted tweet: {tweet}")
                time.sleep(1800)  # Sleep for 30 minutes

        elif action == "meme_tweet":
            logger.debug("Generating a meme tweet.")
            trending_topics = fetch_trending_topics()
            if trending_topics:
                meme_caption = call_openai_with_backoff(f"Create a witty crypto meme caption about: {', '.join(trending_topics)}", model="gpt-3.5-turbo")
                if meme_caption:
                    post_meme(meme_caption)
                    time.sleep(3600)  # Sleep for 1 hour

        elif action == "analyze_trends":
            logger.debug("Analyzing trends using DeepSeek.")
            prompt = "Analyze the latest trends in crypto and provide a summary."
            analysis = fetch_deepseek_response(prompt)
            if analysis:
                tweet = f"📊 Crypto Trend Analysis:\n\n{analysis}"
                check_twitter_rate_limit()
                client.create_tweet(text=tweet)
                TWITTER_RATE_LIMITS["tweets"]["remaining"] -= 1
                logger.info(f"Posted analysis: {tweet}")
                time.sleep(7200)  # Sleep for 2 hours

if __name__ == "__main__":
    logger.debug("Initializing the bot.")
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()