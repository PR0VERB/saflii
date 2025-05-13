# filepath: g:\My Drive\PERSONAL\LEGALPRO\LEGALPRO\CODE\demo\SAFLII_demo_RAG_Retrieval2\api_supabase.py
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import numpy as np
from supabase import create_client, Client
# from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import uvicorn
import traceback
import math
from dotenv import load_dotenv
from embedding_model import api_post # Importing the API post function from embedding_model.py

# Load environment variables from .env file
load_dotenv()

# --- Template Setup ---
templates = Jinja2Templates(directory="templates")

# --- Constants ---
RESULTS_PER_PAGE = 10
MAX_RESULTS = 30 # Max results to fetch from Supabase initially

# --- Model Loading ---
# Still needed for boldening sentences based on query similarity
# model_name = "BAAI/bge-base-en-v1.5"
# model = SentenceTransformer(model_name)

# --- Supabase Setup ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("Error: SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set.")
    # Consider exiting or raising an error if Supabase connection is critical
    supabase: Client | None = None
else:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        print("Supabase client initialized successfully.")
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        supabase = None

# --- Core Logic Functions ---
def get_top_paragraphs_supabase(user_query: str, top_n: int = MAX_RESULTS):
    """
    Retrieve the top paragraphs related to the user query from Supabase
    using a vector similarity search function.
    """
    if not supabase:
        print("Error: Supabase client not initialized.")
        return []
    try:
        # Encode the query
        # query_embedding = model.encode(user_query).tolist()
        query_embedding = api_post({
            "inputs": user_query,
            "parameters": {}
        })[0]
        # print(F'EMBEDDING:{query_embedding}')
        # print(F'EMBEDDING TYPE: {type(query_embedding)}')

        # Call the Supabase database function 'match_cases'
        # Adjust 'match_cases' name if your function is named differently
        # Pass the query embedding and the number of results desired
        response = supabase.rpc(
            'match_cases',
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.5, # Adjust threshold as needed
                'match_count': top_n
            }
        ).execute()

        # Process results
        results = []
        if response.data:
            for item in response.data:
                # Assuming the function returns columns like 'id', 'title', 'paragraph', 'similarity'
                # Adjust keys based on your actual function's return columns
                results.append({
                    "id": item.get('id'), # Assuming 'id' is the primary key or unique identifier
                    "title": item.get('title'), # Assuming 'title' column exists
                    "paragraph": item.get('paragraph'), # Assuming 'paragraph' column exists
                    "score": item.get('similarity'), # Assuming 'similarity' score is returned
                    "filename": item.get('filename') # Assuming 'filename' is returned
                })
        else:
            print(f"Supabase RPC 'match_cases' returned no data or an error: {getattr(response, 'error', 'No error attribute')}")

        # Filter out results with missing essential data before returning
        valid_results = [
            r for r in results
            if r.get("title") and r.get("paragraph") is not None and r.get("score") is not None and r.get("filename")
        ]
        if len(valid_results) < len(results):
             print(f"Warning: Filtered out {len(results) - len(valid_results)} results due to missing data.")

        return valid_results

    except Exception as e:
        print(f"Error in get_top_paragraphs_supabase: {e}")
        traceback.print_exc()
        return []

def bolden_sentences(paragraph: str, user_query: str, top_n_sentences: int = 2):
    """
    Formats the paragraph by boldening the top N most relevant sentences.
    (This function remains largely the same as it operates on text)
    """
    try:
        # Ensure sentences end with a period for consistent splitting
        if not paragraph.strip().endswith('.'):
            paragraph += '.'

        sentences = [s.strip() for s in paragraph.split('.') if s.strip()] # Split and remove empty strings
        if not sentences:
            return []

        # query_embedding = model.encode([user_query])[0]
        # sentence_embeddings = model.encode(sentences)

        query_embedding = api_post({
        "inputs": user_query,
        "parameters": {}
         })[0]
        sentence_embeddings = api_post({
        "inputs": sentences,
        "parameters": {}
         })


        similarities = cosine_similarity([query_embedding], sentence_embeddings)[0]

        # Get the indices of the top N most relevant sentences
        num_to_bold = min(top_n_sentences, len(sentences))
        most_relevant_indices = np.argsort(similarities)[-num_to_bold:]

        formatted_parts = []
        for i, sentence in enumerate(sentences):
            if i in most_relevant_indices:
                # Use <mark> tag for highlighting
                formatted_parts.append(f"<mark>{sentence}</mark>")
            else:
                formatted_parts.append(sentence)

        return formatted_parts
    except Exception as e:
        print(f"Error in bolden_sentences: {e}")
        traceback.print_exc()
        return [s.strip() for s in paragraph.split('.') if s.strip()]

# --- FastAPI Setup ---
app = FastAPI(
    title="SAFLII Case Search (Supabase)",
    description="API for searching South African Constitutional Court cases using Supabase.",
    version="0.4.0" # Version bump
)

# --- Pydantic Model for Response Item ---
class SearchResultStructure(BaseModel):
    filename: str
    link: str # Using title as the link identifier
    relevance_score_percent: int
    formatted_paragraph_parts: list

# --- Helper Function to Render Single Result ---
def render_single_result(request: Request, result_data: dict) -> str:
    """Renders the result_item.html template for a single result."""
    try:
        return templates.TemplateResponse(
            "result_item.html",
            {"request": request, "result": result_data}
        ).body.decode("utf-8")
    except Exception as e:
        print(f"Error rendering result: {e}")
        return templates.TemplateResponse(
            "result_item_error.html",
            {
                "request": request,
                "error_details": f"Error rendering result: {type(e).__name__}",
                "item_title": result_data.get('link', 'N/A') # Use link (title) for error reporting
            }
        ).body.decode("utf-8")

# --- API Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/search/", response_class=HTMLResponse)
async def search_cases(request: Request, user_query: str = Form(...), page: int = Form(1)):
    """Handles search requests and returns paginated results using Supabase."""
    if not supabase:
         return HTMLResponse("<div class='message message-error'>Error: Supabase client not available. Check server logs.</div>", status_code=503) # Service Unavailable

    try:
        if not user_query.strip():
            return HTMLResponse("<div class='message message-error'>Error: Query cannot be empty.</div>", status_code=400)

        print(f"Searching (Supabase) for: {user_query} (Page: {page})")
        # Fetch up to MAX_RESULTS initially from Supabase
        all_top_paragraphs = get_top_paragraphs_supabase(user_query, model, top_n=MAX_RESULTS)
        total_results = len(all_top_paragraphs)
        print(f"Found {total_results} potential paragraphs in total via Supabase.")

        if not all_top_paragraphs:
            return HTMLResponse("<div class='message message-info'>No results found for your query via Supabase.</div>")

        # Calculate pagination
        total_pages = math.ceil(total_results / RESULTS_PER_PAGE)
        current_page = max(1, min(page, total_pages))
        start_index = (current_page - 1) * RESULTS_PER_PAGE
        end_index = start_index + RESULTS_PER_PAGE

        # Get results for the current page
        page_paragraphs_data = all_top_paragraphs[start_index:end_index]

        # Process results for the current page
        page_results_html = []
        for item in page_paragraphs_data:
            try:
                # Data now comes directly from Supabase result
                title = item["title"]
                paragraph = item["paragraph"]
                sim_score = item["score"]
                filename = item["filename"] # Get filename directly

                # Prepare data for template
                formatted_parts = bolden_sentences(paragraph, user_query, model, top_n_sentences=1)
                result_data = SearchResultStructure(
                    filename=filename,
                    link=title, # Use title as the link identifier
                    relevance_score_percent=int(round(sim_score, 2) * 100),
                    formatted_paragraph_parts=formatted_parts
                ).dict()

                # Render HTML for this result
                html_fragment = render_single_result(request, result_data)
                page_results_html.append(html_fragment)

            except Exception as item_error:
                print(f"Error processing item {item.get('title', 'N/A')}: {item_error}")
                traceback.print_exc()
                error_html = templates.TemplateResponse(
                    "result_item_error.html",
                    {
                        "request": request,
                        "error_details": f"Error processing item: {type(item_error).__name__}",
                        "item_title": item.get('title', 'N/A')
                    }
                ).body.decode("utf-8")
                page_results_html.append(error_html)

        # Render pagination controls
        pagination_html = templates.TemplateResponse(
            "pagination.html",
            {
                "request": request,
                "current_page": current_page,
                "total_pages": total_pages,
                "user_query": user_query
            }
        ).body.decode("utf-8")

        # Combine results and pagination
        final_html = "".join(page_results_html) + pagination_html
        return HTMLResponse(final_html)

    except Exception as e:
        print(f"Error in search_cases (Supabase): {e}")
        traceback.print_exc()
        return HTMLResponse(f"<div class='message message-error'>An error occurred: {type(e).__name__}</div>", status_code=500)

if __name__ == "__main__":
    # Use the filename for the app reference if running directly
    uvicorn.run("api_supabase:app", host="0.0.0.0", port=8000, reload=True)

