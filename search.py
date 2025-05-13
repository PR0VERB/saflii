# Remove: import uvicorn
# Remove: from fastapi import FastAPI
# Add:
from fastapi import APIRouter
from embedding_model import api_post # Import the api_post function from embedding_model.py
# Remove: app = FastAPI(...)

# --- Router Setup ---
router = APIRouter()

# --- Assume logger and templates are initialized in api.py ---
# We will import them properly in api.py
import logging
logger = logging.getLogger(__name__)
# from api import templates # This line will be in api.py which imports this router

# --- Workspace count is now retrieved from session in the relevant endpoint ---
# Removed direct import of workspace_items


# --- Model Loading, Supabase Setup, Core Logic Functions (get_top_paragraphs_rpc, etc.) remain the same ---
# ... (keep existing model loading, supabase setup, helper functions) ...
# from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import numpy as np
import math
import re
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse
# Assuming templates is initialized elsewhere (in api.py)
from api import templates # Correct import assuming api.py initializes templates

# --- Constants ---
RESULTS_PER_PAGE = 10
MAX_RESULTS_FETCH = 50 # How many results to initially fetch from DB (adjust as needed)
SIMILARITY_THRESHOLD = 0.5 # Minimum similarity score for DB results (adjust as needed)
HIGHLIGHT_SENTENCES = 2 # How many sentences to highlight in each result

# --- Model Loading ---
# model_name = "BAAI/bge-base-en-v1.5"
# logger.info(f"Loading sentence transformer model: {model_name}...")
# try:
#     model = SentenceTransformer(model_name)
#     logger.info("Model loaded successfully.")
# except Exception as e:
#     logger.error(f"Failed to load SentenceTransformer model: {e}", exc_info=True)
#     # Depending on the application, you might want to exit or handle this differently
#     raise RuntimeError(f"Failed to load SentenceTransformer model: {e}")


# --- Supabase Setup ---
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_RPC_FUNCTION_NAME = "match_paragraphs"

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    logger.error("Supabase credentials (URL or Key) are not set in environment variables.")
    raise ValueError("Supabase credentials are not set in the environment variables.")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    logger.info("Supabase client created.")
except Exception as e:
    logger.error(f"Failed to create Supabase client: {e}", exc_info=True)
    raise RuntimeError(f"Failed to create Supabase client: {e}")


# --- Core Logic Functions ---
# ... (get_top_paragraphs_rpc, split_into_sentences_basic, highlight_relevant_sentences remain unchanged) ...
def get_top_paragraphs_rpc(user_query: str, top_n: int = MAX_RESULTS_FETCH, threshold: float = SIMILARITY_THRESHOLD):
    """
    Retrieve the top paragraphs using Supabase RPC function for similarity search.
    """
    try:
        logger.debug(f"Encoding query for RPC search.") # Changed to debug
        # query_embedding = model.encode(user_query).tolist()
        query_embedding = api_post({
            "inputs": user_query,
            "parameters": {}
            })[0]


        logger.debug(f"Calling Supabase RPC function '{SUPABASE_RPC_FUNCTION_NAME}'...") # Changed to debug
        response = supabase.rpc(
            SUPABASE_RPC_FUNCTION_NAME,
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": top_n,
            },
        ).execute()

        if hasattr(response, 'error') and response.error:
             logger.error(f"Supabase RPC error: {response.error}")
             raise APIError(response.error)
        elif not hasattr(response, 'data'):
             logger.error(f"Supabase RPC response is missing 'data' attribute.")
             return []

        if not response.data:
            logger.info("Supabase RPC returned no matching data.")
            return []

        logger.debug(f"Received {len(response.data)} results from RPC.") # Changed to debug

        formatted_results = []
        for row in response.data:
            # Ensure document_id exists, provide a fallback if necessary (e.g., use htmlsaflii or id)
            doc_id = row.get("document_id")
            if not doc_id:
                 # Fallback strategy: Use htmlsaflii or id if document_id is missing
                 doc_id = row.get("htmlsaflii", row.get("id", f"missing_doc_id_{row.get('id')}"))
                 logger.warning(f"Missing 'document_id' for row id {row.get('id')}, using fallback: {doc_id}")

            formatted_results.append({
                "id": row["id"],
                "title": row["filename"],
                "paragraph": row["paragraph"],
                "score": row["similarity"],
                "htmlsaflii": row["htmlsaflii"],
                "document_id": doc_id # Add document_id
            })
        return formatted_results

    except APIError as api_err:
        logger.error(f"Supabase API Error in get_top_paragraphs_rpc: {api_err}", exc_info=False)
        return []
    except Exception as e:
        logger.error(f"General Error in get_top_paragraphs_rpc: {e}", exc_info=True)
        return []


def split_into_sentences_basic(text: str) -> list[str]:
    """
    Basic sentence splitting based on common punctuation followed by space or end of string.
    """
    if not text:
        return []
    sentences = re.split(r'(?<=[.?!])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]

def highlight_relevant_sentences(paragraph: str, query_embedding: np.ndarray, top_n_sentences: int = HIGHLIGHT_SENTENCES):
    """
    Formats the paragraph by highlighting the top N most relevant sentences using <mark>.
    Uses basic regex splitting for sentences. Matches the user-provided script.

    Args:
        paragraph (str): The input paragraph.
        query_embedding (np.ndarray): The pre-computed embedding of the user query.
        model (SentenceTransformer): The sentence transformer model.
        top_n_sentences (int): Number of top sentences to highlight.

    Returns:
        list[str]: List of sentences, with relevant ones wrapped in <mark> tags.
    """
    try:
        # Use basic regex splitting instead of NLTK
        sentences = split_into_sentences_basic(paragraph)

        if not sentences:
            logger.warning("highlight_relevant_sentences: No sentences found after splitting.")
            return [] # Return empty list as per user script
        if len(sentences) == 1: # Handle single sentence case as per user script
             return [sentences[0]] # Return the sentence unmodified

        # Encode sentences (only if more than one)
        logger.debug(f"Encoding {len(sentences)} sentences for highlighting.")
        # sentence_embeddings = model.encode(sentences)
        sentence_embeddings = api_post({
            "inputs": sentences,
            "parameters": {}
        })

        # Calculate cosine similarity
        logger.debug("Calculating similarities for highlighting.")
        similarities = cosine_similarity([query_embedding], sentence_embeddings)[0]

        # Get indices of top N sentences
        num_to_highlight = min(top_n_sentences, len(sentences))
        # Argsort sorts in ascending order, so take the last 'num_to_highlight' indices for highest similarity
        most_relevant_indices = np.argsort(similarities)[-num_to_highlight:]
        logger.debug(f"Highlighting indices: {most_relevant_indices}")


        formatted_parts = []
        for i, sentence in enumerate(sentences):
            if i in most_relevant_indices:
                formatted_parts.append(f"<mark>{sentence}</mark>")
            else:
                formatted_parts.append(sentence)

        return formatted_parts

    except Exception as e:
        logger.error(f"Error in highlight_relevant_sentences: {e}", exc_info=False) # Log error, avoid traceback here
        # Fallback: return original sentences split by the basic method if error occurs
        return split_into_sentences_basic(paragraph)


# --- Pydantic Model for Response Item ---
class SearchResultStructure(BaseModel):
    # Re-adding fields needed for 'Add to Project'
    id: str
    filename: str
    link: str
    relevance_score_percent: int = Field(..., ge=0, le=100)
    formatted_paragraph_parts: list[str]
    raw_paragraph: str # Needed if the add logic requires it elsewhere
    in_current_project: bool = False # Flag if item is in the specific project context

# --- Helper Function to Render Single Result ---
def render_single_result(request: Request, result_data: dict, user_query: str, current_user: dict | None) -> str:
    """Renders the result_item.html template for a single result. Includes user/query context."""
    try:
        # Ensure the template receives the data in the expected structure
        # The SearchResultStructure model helps enforce this
        return templates.TemplateResponse(
            "result_item.html",
            {"request": request, "result": result_data, "user_query": user_query, "current_user": current_user} # Pass user/query context
        ).body.decode("utf-8")
    except Exception as e:
        logger.error(f"Error rendering result template for item '{result_data.get('filename', 'N/A')}': {e}", exc_info=False)
        return templates.TemplateResponse(
            "result_item_error.html",
            {
                "request": request,
                "error_details": f"Error rendering result: {type(e).__name__}",
                "item_title": result_data.get('filename', 'N/A')
            }
        ).body.decode("utf-8")


# --- API Endpoints ---
# Change @app.get to @router.get, @app.post to @router.post
@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main search page."""
    logger.info("--- Entering read_root ---") # Changed print to logger.info
    logger.info("Attempting to access session...")
    # Get workspace items, user, last query, and last results from session
    session_workspace = request.session.get('workspace', {})
    current_workspace_count = len(session_workspace)
    user = request.session.get('user') # Get user info if logged in
    last_query = request.session.get('last_query', '') # Get last query
    logger.info("Session access complete.")
    # Removed loading last_results_html from session

    logger.debug(f"Serving root page. User: {user.get('email') if user else 'Anonymous'}. Workspace count: {current_workspace_count}. Last Query: '{last_query}'.")

    logger.info("Attempting to render index.html template...")
    # Pass all relevant context to the template
    try:
        response = templates.TemplateResponse("index.html", {
            "request": request,
            "workspace_count": current_workspace_count,
            "user": user, # Pass the user dictionary (or None) as user (matching base.html)
            "last_query": last_query, # Pass last query
            # Removed passing last_results_html to template
        })
        logger.info("--- Successfully rendered index.html template ---")
        return response
    except Exception as e:
        logger.error(f"--- Error rendering index.html template: {e} ---", exc_info=True)
        # Re-raise or return an error response if template rendering fails
        raise HTTPException(status_code=500, detail=f"Internal Server Error: Failed to render template. {e}")

# Allow both GET (for pagination/filtering) and POST (for initial search)
# Allow both GET (for pagination/filtering) and POST (for initial search)
# Define parameters primarily for GET (used by url_for). Read form for POST inside.
@router.api_route("/search/", methods=["GET", "POST"], response_class=HTMLResponse, name="search_cases") # Add name here
async def search_cases(request: Request,
                       user_query: str | None = None, # From query params for GET
                       page: int = 1,              # From query params for GET, default 1
                       unique: bool = False,         # From query params for GET, default False
                       project_id: str | None = None # From query params for GET (optional)
                       ):
    """Handles search requests (POST) and pagination/filtering (GET), performs semantic search via RPC, filters for uniqueness if requested, and returns paginated HTML results."""
    try:
        query_to_use: str | None = None
        page_to_use: int = 1
        project_id_to_use: str | None = None
        unique_filter_active: bool = False

        # Determine parameters based on request method
        if request.method == "POST":
            form_data = await request.form()
            query_to_use = form_data.get("user_query")
            try:
                page_to_use = int(form_data.get("page", 1))
            except (ValueError, TypeError):
                page_to_use = 1
            project_id_to_use = form_data.get("project_id")
            unique_filter_active = False # POST is always initial search, not unique
            logger.debug("Handling POST request for /search/")

        elif request.method == "GET":
            # For GET, parameters are directly injected by FastAPI from query string
            query_to_use = user_query
            page_to_use = page
            project_id_to_use = project_id # Pass project_id if present in GET URL
            unique_filter_active = unique
            logger.debug("Handling GET request for /search/")
        else:
             return HTMLResponse("Method Not Allowed", status_code=405)

        # Validate query
        if not query_to_use:
             return HTMLResponse("<div id='results' class='message message-error'>Error: Search query is missing.</div>", status_code=400)

        query_trimmed = query_to_use.strip()
        if not query_trimmed:
            return HTMLResponse("<div id='results' class='message message-error'>Error: Query cannot be empty.</div>", status_code=400)

        # Determine current page for logic
        current_page_for_logic = max(1, page_to_use)

        logger.info(f"Search request processed. Method: {request.method}, Query: '{query_trimmed}', Page: {current_page_for_logic}, Unique: {unique_filter_active}")

        # --- Check if user is logged in ---
        user = request.session.get('user')
        auth_prompt_html = "" # Keep variable initialized

        # 1. Encode the query ONCE
        query_embedding = api_post({
            "inputs": query_trimmed,
            "parameters": {}
        })[0]

        # 2. Fetch top results using Supabase RPC
        all_top_paragraphs = get_top_paragraphs_rpc(
            query_trimmed, top_n=MAX_RESULTS_FETCH, threshold=SIMILARITY_THRESHOLD
        )

        # --- Filter results if unique flag is active ---
        if unique_filter_active and all_top_paragraphs:
            logger.info("Applying unique filter based on 'document_id'.")
            filtered_paragraphs = []
            seen_document_ids = set()
            for item in all_top_paragraphs:
                # Use 'document_id' as the unique identifier for the source document
                # Ensure 'document_id' exists in the item dictionary
                doc_id = item.get('document_id')
                if doc_id is None:
                    logger.warning(f"Item with id {item.get('id')} missing 'document_id' during filtering. Keeping it.")
                    filtered_paragraphs.append(item) # Keep items without document_id? Or skip? Let's keep for now.
                    continue # Move to next item

                if doc_id not in seen_document_ids:
                    filtered_paragraphs.append(item)
                    seen_document_ids.add(doc_id)
                # else: item is from an already seen document_id, so skip it.

            logger.info(f"Filtered {len(all_top_paragraphs)} results down to {len(filtered_paragraphs)} unique document sources.")
            results_to_paginate = filtered_paragraphs
        else:
            results_to_paginate = all_top_paragraphs # Use all results if not filtering

        total_results_found = len(results_to_paginate)
        logger.info(f"Processing {total_results_found} results for display (max {MAX_RESULTS_FETCH} initially fetched).")

        if not results_to_paginate:
             # Adjust message based on whether filtering happened
             if unique_filter_active:
                 message = "No unique results found matching your query."
             else:
                 message = "No relevant results found matching your query or an error occurred retrieving data."
             # Generate button HTML even for no results, allowing user to switch back if filtered
             import urllib.parse
             encoded_query = urllib.parse.quote_plus(query_trimmed)
             button_html = ""
             if unique_filter_active: # Only show "show all" button if filter is active and returned no results
                 button_url = f"/search/?user_query={encoded_query}&page=1" # Go back to page 1 when clearing filter
                 button_text = "Enable results from same source"
                 button_class = "button button-secondary"
                 button_html = f"""
                 <div style="margin-bottom: 1rem; text-align: center;">
                     <button hx-get="{button_url}" hx-target="#results-area" hx-swap="innerHTML swap:503" hx-indicator="#loading-indicator" hx-push-url="true" class="{button_class}">
                         {button_text}
                     </button>
                 </div>
                 """
             return HTMLResponse(f"{button_html}<div id='results' class='message message-info'>{message}</div>")

        # 3. Paginate the potentially filtered results
        total_pages = math.ceil(total_results_found / RESULTS_PER_PAGE)
        # Use the page number determined earlier for pagination logic
        current_page = max(1, min(current_page_for_logic, total_pages))
        start_index = (current_page - 1) * RESULTS_PER_PAGE
        end_index = start_index + RESULTS_PER_PAGE
        page_paragraphs_data = results_to_paginate[start_index:end_index]
        logger.info(f"Displaying page {current_page}/{total_pages}. Results {start_index + 1}-{min(end_index, total_results_found)} of {total_results_found}.")

        # 4. Check which results are already in the specific project (if project_id is provided)
        # This logic uses page_paragraphs_data, which is already potentially filtered
        existing_paragraph_ids_in_project = set()
        # user variable should already be populated from line 259

        if project_id and user:
            user_id = user.get('id')
            if user_id:
                try:
                    # Verify project ownership first (important for security)
                    project_owner_check = supabase.table('projects').select('id').eq('id', project_id).eq('user_id', user_id).maybe_single().execute()
                    if project_owner_check.data:
                        # Get paragraph IDs for the current page's results
                        # Ensure items have 'id' before list comprehension
                        current_page_paragraph_ids = [item['id'] for item in page_paragraphs_data if 'id' in item]

                        if current_page_paragraph_ids:
                            # Query project_items for these IDs within the specific project
                            items_in_project_response = supabase.table('project_items') \
                                .select('paragraph_id') \
                                .eq('project_id', project_id) \
                                .in_('paragraph_id', current_page_paragraph_ids) \
                                .execute()

                            if items_in_project_response.data:
                                existing_paragraph_ids_in_project = {item['paragraph_id'] for item in items_in_project_response.data}
                                logger.debug(f"Found {len(existing_paragraph_ids_in_project)} items from current results already in project {project_id}")
                    else:
                         logger.warning(f"User {user_id} attempted search context with project {project_id} they don't own.")
                         project_id = None # Invalidate project_id if not owned

                except Exception as db_err:
                    logger.error(f"Error checking project items for project {project_id}: {db_err}", exc_info=True)
                    # Continue without project context if DB check fails
                    project_id = None # Invalidate project_id on error
            else:
                 logger.warning("Could not get user_id from session to check project ownership.")
                 project_id = None # Invalidate if user_id is missing
 
        # 5. Process and render results for the CURRENT page
        page_results_html_fragments = []
        for item in page_paragraphs_data:
            item_title = item.get('title', 'N/A') # Original field name from DB was 'filename'
            try:
                # Ensure 'id' and 'paragraph' exist before proceeding
                if 'id' not in item or 'paragraph' not in item:
                    logger.warning(f"Skipping item due to missing 'id' or 'paragraph': {item.get('title', 'N/A')}")
                    continue # Skip this item if essential data is missing

                item_id = item["id"] # Get the ID from the Supabase result
                paragraph = item["paragraph"] # Raw paragraph
                sim_score = item.get("score", 0.0) # Use .get with default for safety
                # Use the 'htmlsaflii' field from the DB result if available, otherwise construct link
                link = item.get("htmlsaflii", f"/cases/{item_title}") # Fallback link generation

                # Highlight relevant sentences
                formatted_parts = highlight_relevant_sentences(
                    paragraph, query_embedding, top_n_sentences=HIGHLIGHT_SENTENCES
                )

                # Check if this item is in the current project context
                in_current_project = item_id in existing_paragraph_ids_in_project if project_id else False

                # Structure data for the template according to the updated model
                result_data = SearchResultStructure(
                    id=str(item_id),
                    filename=item_title,
                    link=link,
                    relevance_score_percent=int(round(max(0.0, min(1.0, sim_score)) * 100)),
                    formatted_paragraph_parts=formatted_parts,
                    raw_paragraph=paragraph, # Include raw paragraph
                    in_current_project=in_current_project # Pass the flag
                ).dict()

                html_fragment = render_single_result(request, result_data, query_trimmed, user) # Pass user and query
                page_results_html_fragments.append(html_fragment)

            except Exception as item_error:
                logger.error(f"Error processing search result item '{item_title}': {item_error}", exc_info=False)
                error_html = templates.TemplateResponse(
                    "result_item_error.html",
                    {
                        "request": request,
                        "error_details": f"Error processing item: {type(item_error).__name__}",
                        "item_title": item_title
                    }
                ).body.decode("utf-8")
                page_results_html_fragments.append(error_html)

        # 6. Render pagination controls (pass unique flag if active)
        pagination_html = ""
        if total_pages > 1:
            # Need to include the unique flag in pagination links if it's active
            pagination_context = {
                "request": request,
                "current_page": current_page,
                "total_pages": total_pages,
                "user_query": query_trimmed,
                "unique_filter_active": unique_filter_active, # Pass flag to template
                "project_id": project_id_to_use # Pass project_id (can be None)
            }
            # Ensure pagination.html template can handle 'unique_filter_active', 'project_id' and uses correct url_for params
            pagination_html = templates.TemplateResponse(
                "pagination.html", pagination_context
            ).body.decode("utf-8 ") # Potential error source if url_for fails here


        # --- Generate the Filter Button HTML ---
        button_html = ""
        # Only show button if there are results and the original fetch had potential duplicates
        # We check if the number of results *before* filtering is different from *after* filtering,
        # OR if the filter is not active (meaning duplicates might exist).
        potential_duplicates_exist = len(all_top_paragraphs) > len(results_to_paginate)
        # Show button only if results exist AND (duplicates were filtered out OR filter is not currently active)
        show_button_condition = total_results_found > 0 and (potential_duplicates_exist or not unique_filter_active)

        if show_button_condition:
            import urllib.parse
            encoded_query = urllib.parse.quote_plus(query_trimmed) # Ensure query is URL-safe

            params = {'user_query': encoded_query, 'page': 1} # Always reset to page 1 when toggling filter
            if project_id_to_use:
                params['project_id'] = project_id_to_use

            if unique_filter_active:
                # Currently showing unique results, button should link to show all (remove unique flag)
                button_text = "Enable results from same source"
                button_class = "button button-secondary" # Use a standard secondary style
            else:
                # Currently showing all results, button should link to show unique (add unique=true flag)
                params['unique'] = 'true'
                button_text = "Don't show results from the same source"
                button_class = "button button-filter-unique" # Specific class for purple style

            # Construct URL with urlencode
            button_url = f"/search/?{urllib.parse.urlencode(params)}"

            # Generate the button HTML
            button_html = f"""
            <div class="filter-button-container" style="margin-bottom: 1rem; text-align: center;">
                <button hx-get="{button_url}" hx-target="#results-area" hx-swap="innerHTML swap:503" hx-indicator="#loading-indicator" hx-push-url="true" class="{button_class}">
                    {button_text}
                </button>
            </div>
            """

        # 7. Combine button, prompt (if any), results, and pagination
        # Prepend the button HTML
        final_html_content = button_html + auth_prompt_html + "".join(page_results_html_fragments) + pagination_html

        # Append script to explicitly process the new content with HTMX
        # Use htmx.find('#results-area') to ensure we only process the target area
        htmx_process_script = "<script>htmx.process(htmx.find('#results-area'))</script>"
        final_html_content += htmx_process_script

        # 8. Save query to session BEFORE returning response
        request.session['last_query'] = query_trimmed
        # Removed saving last_results_html to session to prevent large cookies
        logger.debug(f"Saved last_query ('{query_trimmed}') to session.")

        return HTMLResponse(content=final_html_content)

    except HTTPException as http_exc:
        logger.warning(f"HTTPException encountered: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e: # Catching generic exceptions, potentially the embedding service issue
        logger.error(f"Unexpected error in /search endpoint: {e}", exc_info=True)
        # Check if query_trimmed exists, otherwise use a placeholder or handle error differently
        query_to_retry = query_trimmed if 'query_trimmed' in locals() else ""
        if not query_to_retry:
             logger.error("Cannot retry search as original query is not available in the exception handler.")
             # Fallback to a generic error if query is missing
             return HTMLResponse("<div id='results' class='message message-error'>An unexpected server error occurred, and the original query could not be retrieved for retry.</div>", status_code=500)

        # Return an empty div for #results-area. The frontend JS will handle the indicator message.
        # Include the retry query in a data attribute on the empty div for the JS to find.
        empty_results_html = f"""<div id="results" data-retry-query="{query_to_retry}" data-retry-trigger="true"></div>"""
        # The data-retry-trigger attribute signals the frontend JS
        # The frontend JS will now read the query from this empty div.
        return HTMLResponse(content=empty_results_html, status_code=503) # Use 503 to indicate temporary unavailability


# --- Remove Run Instruction ---
# Remove: if __name__ == "__main__": ... uvicorn.run(...)
# --- New Endpoint for "More Like This" ---
@router.get("/more_like_this/{paragraph_id}", response_class=HTMLResponse)
async def more_like_this(request: Request, paragraph_id: str, project_item_id: str | None = None):
    """
    Finds and returns up to 5 paragraphs semantically similar to the given paragraph_id.
    Also handles OOB swap for the button, using project_item_id if provided.
    """
    logger.info(f"More Like This request received for paragraph_id: {paragraph_id}, project_item_id: {project_item_id}")
    user = request.session.get('user') # Get user for rendering context

    # 1. Fetch the embedding for the source paragraph
    source_embedding = None
    try:
        # Corrected table name from 'paragraphs' to 'saflii_cases'
        response = supabase.table('saflii_cases') \
            .select('id, embedding') \
            .eq('id', paragraph_id) \
            .maybe_single() \
            .execute()

        if not response.data or not response.data.get('embedding'):
             logger.warning(f"Source paragraph {paragraph_id} not found or lacks embedding. Response data: {response.data}")
             return HTMLResponse(f"<div class='message message-error'>Error: Source paragraph {paragraph_id} not found or could not be retrieved.</div>", status_code=404)

        source_embedding = response.data['embedding']
        logger.debug(f"Successfully fetched embedding for paragraph {paragraph_id}")

    except APIError as e:
        logger.warning(f"APIError fetching source paragraph {paragraph_id}. Error: {e}", exc_info=False)
        return HTMLResponse(f"<div class='message message-error'>Error: Source paragraph {paragraph_id} not found or could not be retrieved.</div>", status_code=404)
    except Exception as e:
        logger.error(f"Unexpected error fetching source paragraph embedding for {paragraph_id}: {e}", exc_info=True)
        return HTMLResponse(f"<div class='message message-error'>Internal server error while fetching source paragraph {paragraph_id}.</div>", status_code=500)

    # 2. Find similar paragraphs using the fetched embedding via RPC
    try:
        # Fetch 6 results: the source itself + 5 similar ones
        SIMILAR_RESULTS_TO_FETCH = 6
        logger.debug(f"Calling RPC to find paragraphs similar to {paragraph_id}")
        response = supabase.rpc(
            SUPABASE_RPC_FUNCTION_NAME,
            {
                "query_embedding": source_embedding,
                "match_threshold": SIMILARITY_THRESHOLD, # Use existing threshold
                "match_count": SIMILAR_RESULTS_TO_FETCH,
            },
        ).execute()

        if hasattr(response, 'error') and response.error:
             logger.error(f"Supabase RPC error (MoreLikeThis): {response.error}")
             raise APIError(response.error)
        elif not hasattr(response, 'data'):
             logger.error(f"Supabase RPC response (MoreLikeThis) is missing 'data' attribute.")
             return HTMLResponse("<div class='message message-info'>No similar results found.</div>") # Return info message

        if not response.data:
            logger.info(f"Supabase RPC (MoreLikeThis) returned no matching data for {paragraph_id}.")
            return HTMLResponse("<div class='message message-info'>No similar results found.</div>") # Return info message

        logger.debug(f"Received {len(response.data)} raw similar results from RPC for {paragraph_id}.")

        # 3. Filter out the source paragraph and limit to 5 results
        similar_paragraphs_data = [
            item for item in response.data if str(item.get('id')) != str(paragraph_id)
        ]
        # Ensure we only take the top 5 *other* results
        top_5_similar = similar_paragraphs_data[:5]
        logger.info(f"Found {len(top_5_similar)} similar paragraphs (excluding source) for {paragraph_id}.")

        if not top_5_similar:
            return HTMLResponse("<div class='message message-info'>No other similar results found.</div>")

        # 4. Process and render the top 5 similar results
        # We'll skip highlighting in 'more like this' results for simplicity by passing user_query=None.

        similar_results_html_fragments = []
        for item in top_5_similar:
            item_title = item.get('filename', 'N/A')
            try:
                if 'id' not in item or 'paragraph' not in item:
                    logger.warning(f"Skipping similar item due to missing 'id' or 'paragraph': {item_title}")
                    continue

                item_id = item["id"]
                paragraph = item["paragraph"]
                sim_score = item.get("similarity", 0.0) # Use 'similarity' from RPC result
                link = item.get("htmlsaflii", f"/cases/{item_title}")

                # Prepare data for rendering - skip highlighting
                # Prepare data specifically for the minimal 'more_like_this_item.html' template
                result_data_minimal = {
                    "filename": item_title,
                    "link": link,
                    "relevance_score_percent": int(round(max(0.0, min(1.0, sim_score)) * 100)),
                    # Add other fields if the minimal template needs them
                }

                # Render the minimal template directly
                html_fragment = templates.TemplateResponse(
                    "partials/more_like_this_item.html",
                    {"request": request, "result": result_data_minimal}
                ).body.decode("utf-8")
                similar_results_html_fragments.append(html_fragment)

            except Exception as item_error:
                # Keep error handling, but maybe simplify the error message display if needed
                logger.error(f"Error processing 'more like this' result item '{item_title}': {item_error}", exc_info=False)
                # Simple error message for the 'more like this' list
                error_html = f"<div class='message message-error' style='font-size: 0.9em;'>Error loading item: {item_title}</div>"
                similar_results_html_fragments.append(error_html)


        # 5. Combine similar results HTML
        similar_results_html = "".join(similar_results_html_fragments)

        # 6. Create OOB swap content to replace the button with a message
        # Use project_item_id if available (from workspace), otherwise fall back to paragraph_id (from search results)
        button_target_id = project_item_id if project_item_id else paragraph_id
        oob_swap_html = f"""
<span id="more-like-this-button-{button_target_id}" hx-swap-oob="true" class="message message-info" style="font-size: 0.9em; padding: 2px 5px; display: inline-block; min-width: 120px; text-align: right; margin-left: 10px;">
    Showing relevant results
</span>
"""
        # 7. Combine the main content (similar results) and the OOB swap
        final_html_content = similar_results_html + oob_swap_html

        # HTMX will automatically process the swapped content (both main target and OOB)
        logger.debug(f"Returning {len(top_5_similar)} similar results and OOB swap for button ID {button_target_id} (paragraph: {paragraph_id})")
        return HTMLResponse(content=final_html_content)

    except APIError as api_err:
        logger.error(f"Supabase API Error in more_like_this RPC call: {api_err}", exc_info=False) # Keep detailed log
        return HTMLResponse("<div class='message message-error'>Error communicating with database to find similar items.</div>", status_code=500)
    except Exception as e:
        logger.error(f"Unexpected error finding similar paragraphs for {paragraph_id}: {e}", exc_info=True)
        return HTMLResponse("<div class='message message-error'>An unexpected server error occurred while finding similar items.</div>", status_code=500)