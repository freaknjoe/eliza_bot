import os
import random
import logging
import threading
from flask import Flask
import tweepy
import nltk
from nltk.chat.util import Chat, reflections
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from time import sleep

# Ensure NLTK resources are available
nltk.download("punkt")

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TwitterBot")

# Flask setup for Render port binding
app = Flask(__name__)

@app.route('/')
def home():
    return "Twitter bot is running!"

def start_flask():
    app.run(host='0.0.0.0', port=10000)

# Fetch credentials from environment variables
API_KEY = os.getenv('TWITTER_API_KEY')
API_SECRET_KEY = os.getenv('TWITTER_API_SECRET_KEY')
ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

# Validate that all credentials are set
if not all([API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    raise ValueError("Twitter API credentials are not properly set as environment variables.")

# Authenticate with Twitter
auth = tweepy.OAuthHandler(API_KEY, API_SECRET_KEY)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

# ELIZA chatbot setup
pairs = [
    [r"I want to invest in (.*)", ["Why do you want to invest in %1?", "Have you considered $FEDJA?"]],
    [r"(.*)crypto(.*)", ["$FEDJA is the next big thing in crypto! 🐾💎", "Join the memecoin revolution with $FEDJA!"]],
    [r"(.*)", ["Check out $FEDJA, the hottest memecoin on Solana! 🚀", "Invest smart, invest in $FEDJA."]],
]
chatbot = Chat(pairs, reflections)

# Path to the images folder
images_folder = "images"  # Assumes the folder is in the project root

# Meme creation setup
def create_meme(image_path, caption):
    """Overlay text on an image to create a meme."""
    try:
        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            width, height = img.size
            text_width, text_height = draw.textsize(caption, font=font)
            x = (width - text_width) // 2
            y = height - text_height - 20
            draw.text((x, y), caption, font=font, fill="white")
            output_path = "meme_output.jpg"
            img.save(output_path)
            return output_path
    except Exception as e:
        logger.error(f"Error creating meme: {e}")
        return None

# Post a tweet
def post_tweet(content):
    try:
        api.update_status(content)
        logger.info("Tweet posted successfully.")
    except Exception as e:
        logger.error(f"Error posting tweet: {e}")

# Post a meme
def post_meme():
    try:
        if not os.path.exists(images_folder):
            logger.error(f"Images folder '{images_folder}' does not exist.")
            return

        images = os.listdir(images_folder)
        if not images:
            logger.warning("No images found in the images folder.")
            return

        image_path = os.path.join(images_folder, random.choice(images))
        captions = [
            "When $FEDJA takes off 🚀😸",
            "HODLing $FEDJA like a boss 🐾💰",
            "$FEDJA is the cat's meow in crypto!",
        ]
        caption = random.choice(captions)
        meme_path = create_meme(image_path, caption)
        if meme_path:
            api.update_with_media(meme_path, caption)
            logger.info("Meme posted successfully.")
    except Exception as e:
        logger.error(f"Error posting meme: {e}")

# Main bot logic
def run_bot():
    while True:
        now = datetime.now()
        if now.hour % 4 == 0:  # Post every 4 hours
            if random.random() < 0.7:
                # 70% chance to post an ELIZA response
                message = chatbot.respond("What is $FEDJA?")
                post_tweet(message)
            else:
                # 30% chance to post a meme
                post_meme()

        logger.info("Sleeping for an hour...")
        sleep(3600)  # Sleep for an hour

if __name__ == "__main__":
    # Start Flask server in a separate thread for Render port binding
    threading.Thread(target=start_flask).start()
    # Start the Twitter bot
    run_bot()
