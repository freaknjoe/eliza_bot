import os
import random
import json
import logging
import threading
from flask import Flask
import tweepy
from PIL import Image, ImageDraw, ImageFont
from time import sleep
from datetime import datetime
import openai

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TwitterBot")

# Flask setup for Render port binding
app = Flask(__name__)

@app.route('/')
def home():
    return "Crypto, AI, and Memecoin Bot with DeepSeek and OpenAI is running!"

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

# Validate Twitter API credentials
if not all([API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    raise ValueError("Twitter API credentials are not properly set as environment variables.")

# Authenticate with Twitter
auth = tweepy.OAuthHandler(API_KEY, API_SECRET_KEY)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

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

# Dynamic prompts
def get_random_prompt():
    """Get a random prompt from a predefined list."""
    prompts = [
        "Why is $FEDJA the best memecoin on Solana?",
        "What are the latest advancements in DeFi?",
        "How does AI impact the future of blockchain?",
        "What are the risks and rewards of investing in memecoins?"
    ]
    return random.choice(prompts)

# Fetch reasoning from DeepSeek
def fetch_deepseek_response(user_prompt):
    """Fetch reasoning content from DeepSeek."""
    try:
        openai.api_key = DEEPSEEK_API_KEY
        deepseek_client = openai.OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com/v1"
        )

        deepseek_response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": user_prompt}]
        )
        reasoning_content = deepseek_response.choices[0].message.content.strip()
        return reasoning_content
    except Exception as e:
        logger.error(f"Error fetching DeepSeek response: {e}")
        return "DeepSeek is currently unavailable. Stay tuned!"

# Fetch final response from OpenAI
def fetch_openai_response(user_prompt, reasoning_content):
    """Use OpenAI GPT to refine the DeepSeek reasoning."""
    try:
        openai.api_key = OPENAI_API_KEY
        system_prompt = f"""
        You are a helpful assistant. Below is the reasoning provided by DeepSeek:
        {reasoning_content}
        
        Now, answer the following question in a clear and concise way:
        {user_prompt}
        """
        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        final_response = gpt_response.choices[0].message.content.strip()
        return final_response
    except Exception as e:
        logger.error(f"Error fetching OpenAI response: {e}")
        return "OpenAI is currently unavailable. Stay tuned!"

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
            # Post a regular tweet
            user_prompt = get_random_prompt()
            reasoning_content = fetch_deepseek_response(user_prompt)
            final_response = fetch_openai_response(user_prompt, reasoning_content)
            post_tweet(final_response)

        elif action == "meme_tweet":
            # Post a meme tweet
            user_prompt = get_random_prompt()
            reasoning_content = fetch_deepseek_response(user_prompt)
            final_response = fetch_openai_response(user_prompt, reasoning_content)
            image_name = random.choice(os.listdir(IMAGES_FOLDER))  # Pick a random image
            meme_path = create_meme(image_name, final_response)
            if meme_path:
                post_tweet(final_response, meme_path)

        elif action == "interact":
            # Reply to mentions
            reply_to_mentions()

        # Update memory
        update_memory(user_prompt, final_response)

        # Sleep for 15 minutes before the next action
        logger.info("Sleeping for 15 minutes...")
        sleep(900)

if __name__ == "__main__":
    # Start Flask server in a separate thread for Render port binding
    threading.Thread(target=start_flask, daemon=True).start()
    # Start the bot
    run_bot()