from dotenv import load_dotenv
import requests
import os

load_dotenv() # Load environment variables from .env file

def api_post(payload):
    API_URL = os.getenv("HF_EMBEDDING_API_URL")
    token = os.getenv("HF_TOKEN")
    headers = {
    "Accept" : "application/json",
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json" 
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()


# for i in range(40):

#     query_embedding = api_post({
#         "inputs": f"{i}",
#         "parameters": {}
#     })[0]
#     print(query_embedding)



# import requests
# import os
# from dotenv import load_dotenv

# load_dotenv() # Load environment variables from .env file for local dev

# HF_API_TOKEN = os.environ.get("HF_TOKEN")
# # Example model, replace with your chosen model
# MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
# API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
# HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}

# def get_embeddings_hf_api(texts):
#     """Gets embeddings for a list of texts using Hugging Face Inference API."""
#     if not HF_API_TOKEN:
#         raise ValueError("Hugging Face API token not configured.")

#     try:
#         response = requests.post(API_URL, headers=HEADERS, json={"inputs": texts})
#         response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
#         result = response.json()
#         # The structure of the result might vary slightly based on the model
#         if isinstance(result, list) and isinstance(result[0], list):
#              return result # Assuming the API returns a list of embeddings
#         else:
#              # Handle potential errors or unexpected response format
#              print(f"Unexpected API response format: {result}")
#              return None # Or raise an error
#     except requests.exceptions.RequestException as e:
#         print(f"Error calling Hugging Face API: {e}")
#         # Handle connection errors, timeouts, etc.
#         return None
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         # Handle JSON decoding errors or other issues
#         return None

# # --- Usage Example ---
# # sentences = ["This is the first sentence.", "Here is another one."]
# # embeddings = get_embeddings_hf_api(sentences)
# # if embeddings:
# #     print(f"Received {len(embeddings)} embeddings.")
# #     # Process embeddings...
# # else:
# #     print("Failed to get embeddings.")
