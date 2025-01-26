import os
import logging
import threading
from flask import Flask
import tweepy
import openai
from datetime import datetime
from time import sleep

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IntelligentTwitterBot")

# Flask setup for Render port binding
app = Flask(__name__)

@app.route('/')
def home():
    return "Intelligent Twitter bot is running with DeepSeek and OpenAI integration!"

def start_flask():
    # Use the PORT environment variable for Render
    port = int(os.environ.get("PORT", 10000))  # Default to 10000 if PORT is not set
    app.run(host='0.0.0.0', port=port)

# Fetch credentials from environment variables
API_KEY = os.getenv('TWITTER_API_KEY')
API_SECRET_KEY = os.getenv('TWITTER_API_SECRET_KEY')
ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

# Fetch API keys for DeepSeek and OpenAI
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Validate Twitter API credentials
if not all([API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET]):
    raise ValueError("Twitter API credentials are not properly set as environment variables.")

# Authenticate with Twitter
auth = tweepy.OAuthHandler(API_KEY, API_SECRET_KEY)
auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

# Fetch reasoning from DeepSeek and OpenAI
def get_intelligent_response(user_prompt):
    """Generate a response using DeepSeek and OpenAI."""
    try:
        # Set up DeepSeek client
        openai.api_key = DEEPSEEK_API_KEY
        deepseek_client = openai.OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com/v1"
        )

        # Get reasoning from DeepSeek
        deepseek_response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": user_prompt}]
        )
        reasoning_content = deepseek_response.choices[0].message.content
        logger.info("DeepSeek Reasoning Content: %s", reasoning_content)

        # Get final response from OpenAI
        openai.api_key = OPENAI_API_KEY
        system_prompt = f"""
        You are a helpful assistant. Below is the reasoning provided by DeepSeek:
        {reasoning_content}
        
        Now, answer the following question in a clear and concise way:
        {user_prompt}
        """
        gpt4_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        final_response = gpt4_response.choices[0].message.content
        logger.info("GPT-4 Final Response: %s", final_response)
        return final_response
    except Exception as e:
        logger.error(f"Error in DeepSeek/OpenAI integration: {e}")
        return None

# Post a tweet
def post_tweet(content):
    try:
        api.update_status(content)
        logger.info("Tweet posted successfully.")
    except Exception as e:
        logger.error(f"Error posting tweet: {e}")

# Main bot logic
def run_bot():
    while True:
        # Query DeepSeek and OpenAI for a response
        user_prompt = "Explain why $FEDJA is a great investment for crypto enthusiasts."
        final_response = get_intelligent_response(user_prompt)
        if final_response:
            post_tweet(final_response)

        logger.info("Sleeping for 15 minutes...")
        sleep(900)  # Sleep for 15 minutes (900 seconds)

if __name__ == "__main__":
    # Start Flask server in a separate thread for Render port binding
    threading.Thread(target=start_flask).start()
    # Start the Twitter bot
    run_bot()
