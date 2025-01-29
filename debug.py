from requests_oauthlib import OAuth1
import requests

# Replace these with your actual credentials
ACCESS_TOKEN="1878624202229493760-XnrDoLvUcDCWn7Vp5rhF0vZeFCBgVl"
ACCESS_TOKEN_SECRET="LwOqYIR2pTL2W4w5UXp1zDT8oGSsjc1ovFZZjlyU8Bf5M"
API_KEY="6oFrg8RrVKbBcgTGQtcpYcs9e"
API_SECRET_KEY="olnENjEYj8fUKQCwsw24GPHjgt3NFtvHRbPOKty1ViB8GCAoc6"

# Twitter API v2 endpoint for posting tweets
url = "https://api.twitter.com/2/tweets"

# OAuth 1.0a authentication
auth = OAuth1(API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

# Data payload for the tweet
data = {
    "text": "Hello, world! This is a test tweet from my Python script."
}

try:
    # Make the POST request to the Twitter API
    response = requests.post(url, auth=auth, json=data)
    response.raise_for_status()  # Raises an HTTPError for bad responses

    # Print the response if successful
    print("Tweet posted successfully!")
    print(response.json())

except requests.exceptions.HTTPError as err:
    # Handle errors
    print(f"Error: {err}")
    print(f"Response: {response.text}")
