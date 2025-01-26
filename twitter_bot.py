import os
import random
import json
import logging
import threading
import requests
from flask import Flask
import tweepy
from PIL import Image, ImageDraw, ImageFont
from time import sleep
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

# Authenticate with Twitter
auth = tweepy.OAuthHandler(API_KEY, API_SECRET_KEY)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

# Initialize OpenAI and DeepSeek clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")

# Path to the images folder (uploaded to GitHub)
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

# Fetch trending crypto topics from CryptoPanic
def fetch_trending_topics():
    """Fetch trending crypto topics from CryptoPanic."""
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}"
        response = requests.get(url)
        if response.status_code == 200:
            news_items = response.json()["results"]
            trending_topics = []
            for item in news_items:
                if "title" in item:
                    trending_topics.append(item["title"])
            return trending_topics[:5]  # Return top 5 trending topics
        else:
            logger.error(f"Failed to fetch trending topics: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
        return []

# Meme generation function
def create_meme(image_name, caption):
    """Overlay text on an image to create a meme."""
    try:
        image_path = os.path.join(IMAGES_FOLDER, image_name)
        if not os.path.exists(image_path):
            logger.error(f"Image {image_name} not found in {IMAGES_FOLDER}.")
            return None

        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)

            # Calculate text size using textbbox
            text_bbox = draw.textbbox((0, 0), caption, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # Determine text position
            width, height = img.size
            x = (width - text_width) // 2
            y = height - text_height - 20

            # Draw the text
            draw.text((x, y), caption, font=font, fill="white")

            # Save the image with the meme
            output_path = "meme_output.jpg"
            img.save(output_path)
            return output_path
    except Exception as e:
        logger.error(f"Error creating meme: {e}")
        return None

# Memory system
def load_memory():
    """Load past interactions from a file."""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"prompts": [], "responses": []}

def save_memory(memory):
    """Save interactions to a file."""
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f)

def update_memory(prompt, response):
    """Update the bot's memory with a new interaction."""
    memory = load_memory()
    memory["prompts"].append(prompt)
    memory["responses"].append(response)
    save_memory(memory)

# Generate a unique prompt dynamically with trending crypto topics
def generate_unique_prompt():
    """Use OpenAI to generate a unique and engaging prompt with trending crypto topics."""
    try:
        trending_topics = fetch_trending_topics()
        if trending_topics:
            trending_text = ", ".join(trending_topics)
            prompt_request = f"""
            Come up with a unique and engaging question or statement about crypto, memes, AI, DeFi, or DeFiAI.
            Use a witty and mildly sarcastic tone. Avoid outright jokes.
            Incorporate these trending crypto topics: {trending_text}.
            """
        else:
            prompt_request = """
            Come up with a unique and engaging question or statement about crypto, memes, AI, DeFi, or DeFiAI.
            Use a witty and mildly sarcastic tone. Avoid outright jokes.
            """
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",  # Use GPT-3.5
            messages=[
                {"role": "system", "content": "You are a witty and mildly sarcastic assistant focused on crypto, memes, AI, DeFi, and DeFiAI."},
                {"role": "user", "content": prompt_request}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error generating unique prompt: {e}")
        return "What's the future of crypto? Probably more volatility and memes. 🚀 #Crypto"

# Fetch reasoning content from DeepSeek
def fetch_deepseek_response(user_prompt):
    """Fetch reasoning content from DeepSeek."""
    try:
        deepseek_response = deepseek_client.chat.completions.create(
            model='deepseek-chat',
            messages=[{"role": "user", "content": user_prompt}]
        )
        reasoning_content = deepseek_response.choices[0].message.content
        return reasoning_content
    except Exception as e:
        logger.error(f"Error fetching DeepSeek response: {e}")
        return "DeepSeek is currently unavailable. But hey, I'm still here. 😅 #Crypto #AI #DeFi"

# Generate a witty and mildly sarcastic response using OpenAI
def fetch_openai_response(user_prompt, reasoning_content):
    """Use OpenAI GPT to refine the DeepSeek reasoning with a witty/sarcastic tone."""
    try:
        system_prompt = f"""
        You are a witty and mildly sarcastic assistant focused on crypto, memes, AI, DeFi, and DeFiAI.
        Below is the reasoning provided by DeepSeek:
        {reasoning_content}

        Now, answer the following question in a clear, concise, and mildly sarcastic way:
        {user_prompt}
        """
        gpt_response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",  # Use GPT-3.5
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        final_response = gpt_response.choices[0].message.content
        return final_response
    except Exception as e:
        logger.error(f"Error fetching OpenAI response: {e}")
        return "OpenAI is currently unavailable. But hey, at least I'm still here. 😅 #Crypto #AI #DeFi"

# Generate a witty and mildly sarcastic meme caption dynamically
def generate_meme_caption():
    """Use OpenAI to generate a witty and mildly sarcastic caption for a meme."""
    try:
        trending_topics = fetch_trending_topics()
        if trending_topics:
            trending_text = ", ".join(trending_topics)
            caption_request = f"""
            Come up with a witty and mildly sarcastic caption for a crypto meme.
            Make it relatable to the crypto community and include emojis if possible.
            Avoid outright jokes.
            Incorporate these trending crypto topics: {trending_text}.
            """
        else:
            caption_request = """
            Come up with a witty and mildly sarcastic caption for a crypto meme.
            Make it relatable to the crypto community and include emojis if possible.
            Avoid outright jokes.
            """
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",  # Use GPT-3.5
            messages=[
                {"role": "system", "content": "You are a witty and mildly sarcastic assistant focused on crypto memes."},
                {"role": "user", "content": caption_request}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error generating meme caption: {e}")
        return "When you buy the dip, but it keeps dipping... because of course it does. 😅 #CryptoMemes"

# Post a tweet
def post_tweet(content, image_path=None):
    """Post a tweet with optional image."""
    try:
        if image_path:
            api.update_status_with_media(content, image_path)
        else:
            api.update_status(content)
        logger.info("Tweet posted successfully.")
    except Exception as e:
        logger.error(f"Error posting tweet: {e}")

# Reply to mentions
def reply_to_mentions():
    """Reply to tweets that mention the bot."""
    try:
        mentions = api.mentions_timeline(count=5)  # Fetch the latest 5 mentions
        for mention in mentions:
            if not mention.favorited:  # Avoid replying to the same mention twice
                user_prompt = mention.text.replace("@YourBotName", "").strip()
                reasoning_content = fetch_deepseek_response(user_prompt)
                final_response = fetch_openai_response(user_prompt, reasoning_content)
                api.update_status(
                    status=f"@{mention.user.screen_name} {final_response}",
                    in_reply_to_status_id=mention.id
                )
                logger.info(f"Replied to mention from @{mention.user.screen_name}")
                mention.favorite()  # Mark the mention as favorited to avoid duplicate replies
    except Exception as e:
        logger.error(f"Error replying to mentions: {e}")

# Main bot logic
def run_bot():
    while True:
        # Rotate between regular tweets, meme tweets, and interactions
        action = random.choice(["regular_tweet", "meme_tweet", "interact"])

        if action == "regular_tweet":
            # Generate a unique prompt and post a regular tweet
            user_prompt = generate_unique_prompt()
            reasoning_content = fetch_deepseek_response(user_prompt)
            final_response = fetch_openai_response(user_prompt, reasoning_content)
            post_tweet(final_response)
            # Update memory only for regular tweets
            update_memory(user_prompt, final_response)

        elif action == "meme_tweet":
            # Generate a meme caption and post a meme tweet
            caption = generate_meme_caption()
            image_name = random.choice(os.listdir(IMAGES_FOLDER))  # Pick a random image
            meme_path = create_meme(image_name, caption)
            if meme_path:
                post_tweet(caption, meme_path)

        elif action == "interact":
            # Reply to mentions
            reply_to_mentions()

        # Sleep for 15 minutes before the next action
        logger.info("Sleeping for 15 minutes...")
        sleep(900)

if __name__ == "__main__":
    # Start Flask server in a separate thread for Render port binding
    threading.Thread(target=start_flask, daemon=True).start()
    # Start the bot
    run_bot()