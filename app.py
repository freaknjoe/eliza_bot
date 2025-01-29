import os
import random
import time
import logging
import requests
from flask import Flask
import tweepy
from datetime import datetime
from PIL import Image
import threading
import re
import openai

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
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CRYPTOPANIC_API_KEY = os.getenv('CRYPTOPANIC_API_KEY')

# Constants for $FEDJA
FEDJA_CONTRACT_ADDRESS = "9oDw3Q36a8mVHfPCSmxYBXE9iLeJjsCYu97JGpPwDvVZ"
FEDJA_TWITTER_TAG = "@Fedja_SOL"
IMAGES_FOLDER = "images"  # Folder containing images for posts

# Validate API credentials
if not all([API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, OPENAI_API_KEY, CRYPTOPANIC_API_KEY]):
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

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

# Function to load prompts from a file
def load_prompts(file_path):
    """Load prompts from a specified file into a list."""
    try:
        with open(file_path, 'r') as file:
            prompts = [line.strip() for line in file if line.strip()]
        return prompts
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return []

# Load prompts from files
FEDJA_PROMPTS = load_prompts('fedja_prompts.txt')
GENERAL_CRYPTO_PROMPTS = load_prompts('general_crypto_prompts.txt')

def fetch_cryptopanic_topics():
    """Fetch trending topics from CryptoPanic filtered for relevant categories."""
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()

        # Extract relevant topics
        results = response.json().get("results", [])
        relevant_topics = [
            item["title"] for item in results if any(
                keyword in item["title"].lower() for keyword in ["memecoin", "defi", "ai", "defiai", "btc", "eth", "solana"]
            )
        ]
        return relevant_topics[:5]
    except Exception as e:
        logger.error(f"Error fetching topics from CryptoPanic: {e}")
        return []

def call_openai(prompt, model="gpt-3.5-turbo"):
    """Fetch a response from OpenAI API."""
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7,
            top_p=0.9
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        return None

def chunk_text(text, chunk_size=1000):
    """Chunk the text into smaller sections of specified size."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

def summarize_text(text):
    """Summarize the given text into a concise version using OpenAI, ensuring it's 280 characters or less."""
    try:
        # Split the text into chunks if it's too long
        chunks = chunk_text(text)
        summaries = []

        for chunk in chunks:
            prompt = f"Summarize the following text in 280 characters or less: {chunk}"
            summary = call_openai(prompt, model="gpt-3.5-turbo")
            if summary:
                summaries.append(summary)

        # Combine all summaries into one
        combined_summary = " ".join(summaries)

        # Ensure the combined summary is within 280 characters
        if len(combined_summary) > 280:
            combined_summary = combined_summary[:280]

        # Final check to ensure the summary is not empty
        if not combined_summary:
            logger.warning("Summarization failed or exceeded character limit.")
            return None

        return combined_summary

    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
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

def get_fallback_prompt(category):
    """Get a random fallback prompt from the specified category."""
    if category == "fedja":
        return random.choice(FEDJA_PROMPTS) if FEDJA_PROMPTS else "Default $FEDJA prompt."
    elif category == "general_crypto":
        return random.choice(GENERAL_CRYPTO_PROMPTS) if GENERAL_CRYPTO_PROMPTS else "Default general crypto prompt."
    else:
        return "Default prompt."

def generate_and_post_tweet(base_prompt, category="general_crypto"):
    """Generate a detailed text, summarize it to 280 characters or less, and post as a tweet."""
    try:
        # Generate detailed text
        detailed_text = call_openai(base_prompt, model="gpt-3.5-turbo")
        if not detailed_text:
            logger.warning("Failed to generate detailed text. Using fallback.")
            detailed_text = get_fallback_prompt(category)
        
        # Summarize the detailed text to 280 characters or less
        summarized_text = summarize_text(detailed_text)
        if not summarized_text:
            logger.warning("Summarization failed. Using fallback prompt.")
            final_tweet = get_fallback_prompt(category)
        else:
            final_tweet = summarized_text

        # Ensure the final tweet is 280 characters or less
        if len(final_tweet) > 280:
            logger.warning("Final tweet exceeds 280 characters. Using fallback.")
            final_tweet = get_fallback_prompt(category)

        # If the final tweet is still too long, use a short fallback
        if len(final_tweet) > 280:
            final_tweet = random.choice([
                "Crypto is wild today! 🚀 #CryptoChat",
                "AI is changing everything! 🤖 #CryptoTech",
                "DeFi is the future! 📈 #DeFiInsight",
                "Memecoins are here to stay! 🐕 #MemeCoins",
            ])
            logger.warning("Using short fallback tweet.")

        logger.info(f"Final tweet: {final_tweet}")
        
        image_path = None

        # Append $FEDJA reference if applicable
        if category == "fedja":
            # Randomly choose between including the contract address or Twitter tag
            reference_type = random.choice(["contract", "twitter"])
            
            if reference_type == "contract":
                fedja_reference = f"\n\n$FEDJA | {FEDJA_CONTRACT_ADDRESS} 🐕 #FedjaFren"
            else:
                fedja_reference = f"\n\nCheck out {FEDJA_TWITTER_TAG} for more info! 🐕 #FedjaMoon"
            
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
            response = client_v2.create_tweet(text=text, media_ids=[media.media_id_string])
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
    """Post a positive and witty tweet about $FEDJA with an image."""
    image_path = select_random_image()
    if image_path:
        base_prompt = f"Create a detailed, positive, and witty paragraph about $FEDJA, a memecoin on Solana. Discuss its potential, community, and recent developments. Keep it under 280 characters. #FedjaFren"
        generate_and_post_tweet(base_prompt, category="fedja")
    else:
        logger.warning("No images found in the images folder. Posting without image.")
        base_prompt = f"Create a detailed, positive, and witty paragraph about $FEDJA, a memecoin on Solana. Discuss its potential, community, and recent developments. Keep it under 280 characters. #FedjaMoon"
        generate_and_post_tweet(base_prompt, category="fedja")

def post_regular_tweet():
    """Post a tweet about crypto, AI, or DeFi using trending topics from CryptoPanic and OpenAI summarization."""
    try:
        # Fetch trending topics from CryptoPanic
        topics = fetch_cryptopanic_topics()
        if not topics:
            logger.warning("No trending topics found. Using fallback prompt.")
            generate_and_post_tweet(get_fallback_prompt("general_crypto"), category="general_crypto")
            return

        # Concatenate topics into a single string
        topics_text = "\n".join(topics)

        # Create a prompt to summarize the topics
        prompt = f"Summarize the following trending crypto topics into a single, witty, mildly sarcastic paragraph under 280 characters:\n{topics_text}\n#CryptoChat"
        
        # Generate the summarized text
        summarized_text = call_openai(prompt, model="gpt-3.5-turbo")
        
        if not summarized_text or len(summarized_text) > 280:
            logger.warning("Summarization failed or exceeded character limit. Using fallback prompt.")
            generate_and_post_tweet(get_fallback_prompt("general_crypto"), category="general_crypto")
            return

        # Post the summarized tweet
        post_tweet(summarized_text, image_path=None)

    except Exception as e:
        logger.error(f"Error in post_regular_tweet: {e}")
        return None

def run_bot():
    """Main bot loop."""
    logger.info("Starting the bot.")
    while True:
        # Randomly select action with 20% chance for $FEDJA posts
        if random.random() < 0.2:
            action = "fedja_tweet"
        else:
            action = "regular_tweet"
        
        logger.info(f"Selected action: {action}")

        if action == "fedja_tweet":
            post_fedja_tweet()
            time.sleep(43200)  # Post about $FEDJA every 12 hours

        elif action == "regular_tweet":
            post_regular_tweet()
            time.sleep(1800)  # Sleep for 30 minutes

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()