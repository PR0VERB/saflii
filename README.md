# To do
Padding especially on workspace

Make a dashboard to reflect your recent activity and latest articles related to yours. something we could use for the regulation thing 

# SAFLII Case Search & Workspace

This project provides a web application for searching paragraphs within South African Constitutional Court (SAFLII) cases using semantic search and managing a personal workspace of saved paragraphs.

## Features (Page by Page)

### Authentication (`/login`, `/signup`, `/profile`)

*   **Login Page (`/login`):** Secure user login with email and password via Supabase Auth. Redirects to the main search page on success.
*   **Signup Page (`/signup`):** New user registration (name, surname, email, password). Requires email confirmation via Supabase.
*   **Profile Page (`/profile`):** Logged-in users can view their email and update their name. Changes are saved to Supabase.
*   **Logout (`POST /logout`):** Clears the user's session and attempts Supabase sign-out. Redirects to the main search page.

### Search & Results (`/`, `POST /search/`)

*   **Main Search Page (`/`):**
    *   Primary interface for entering search queries.
    *   Displays the user's last search query (if any).
    *   Shows the number of projects the user has (if logged in).
*   **Search Submission (`POST /search/`):**
    *   Performs semantic search using Sentence Transformers (`BAAI/bge-base-en-v1.5`) and Supabase `pgvector` RPC function (`match_paragraphs`).
    *   Displays paginated search results (10 per page) dynamically using HTMX.
    *   Highlights the most relevant sentences within each result paragraph using `<mark>`.
    *   Shows a relevance score (0-100%) for each result.
    *   Provides a link to the full case document (`htmlsaflii` field from DB).
    *   Includes pagination controls.
    *   If logged in and searching within a project context, flags results already present in that project.
    *   Allows logged-in users to add results to their projects directly from the search results page.

### Workspace & Projects (`/workspace/`, `/projects/...`)

*   **Workspace Page (`/workspace/`):**
    *   Displays a list of the logged-in user's projects.
    *   Includes a form to create new projects (name and optional description).
    *   Requires login.
*   **Project Creation (`POST /projects/create`):**
    *   Handles new project creation, saving to the database.
    *   Updates the project list dynamically (e.g., in the sidebar via HTMX trigger `projectListChanged`).
    *   Requires login.
*   **Project Detail Page (`/projects/{project_id}`):**
    *   Dedicated page showing details for a single project (name, description).
    *   Lists all paragraphs/items added to the project.
    *   Allows reordering of items via drag-and-drop (`POST /api/project_items/reorder`).
    *   Allows adding comments to items (persisted in DB).
    *   Allows removing items from the project (`DELETE /project_items/{project_item_id}`).
    *   Requires login and project ownership.
*   **Adding Items:**
    *   **Get Form (`GET /workspace/get_add_to_project_form/{paragraph_id}`):** Dynamically loads a form within search results, allowing users to select a project (or create a new one) to add the paragraph to. Disables projects where the item already exists.
    *   **Add Item (`POST /project_items/add`):** Saves the link between a paragraph and a project, including the original search query and an optional comment. Requires login and project ownership.
*   **Sidebar (`GET /workspace/sidebar_projects`):**
    *   Dynamically loaded list of user's projects for the sidebar navigation. Highlights the currently viewed project.
*   **Export (`GET /export/html/{paragraph_id}`):**
    *   Retrieves and displays the raw HTML content (`htmlsaflii`) of a specific saved paragraph.

## Technology Stack

*   **Backend:** Python, FastAPI
*   **Server:** Uvicorn
*   **Frontend:** HTML, CSS, HTMX, Jinja2 Templates
*   **Semantic Search:** Sentence Transformers (`BAAI/bge-base-en-v1.5` model)
*   **Vector Database & Search:** Supabase (Postgres with pgvector extension, using RPC for search)

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```
2.  **Create Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # Activate the environment
    # Windows:
    .\venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set Up Environment Variables:**
    *   Copy the example environment file: `cp .env.example .env`
    *   Edit the `.env` file and add your Supabase project URL and Anon Key:
        ```dotenv
        SUPABASE_URL=your_supabase_url_here
        SUPABASE_ANON_KEY=your_supabase_anon_key_here
        ```

## Running the Application

1.  **Start the Server:**
    ```bash
    uvicorn api:app --reload --host 0.0.0.0 --port 8000
    ```
    *   `--reload`: Enables auto-reloading during development.
    *   `--host 0.0.0.0`: Makes the server accessible on your network. Use `127.0.0.1` for local access only.
    *   `--port 8000`: Specifies the port.

2.  **Access the Application:** Open your web browser and navigate to `http://localhost:8000` or `http://127.0.0.1:8000`.

## Environment Variables

The application requires the following environment variables defined in a `.env` file in the project root:

*   `SUPABASE_URL`: Your Supabase project URL.
*   `SUPABASE_ANON_KEY`: Your Supabase project's public anonymous key.

## Supabase Setup Notes

This application assumes you have a Supabase project set up with:

*   A table containing case paragraphs and their embeddings.
*   The `pgvector` extension enabled.
*   An RPC function named `match_paragraphs` (or similar, defined in `search.py`) that performs a vector similarity search based on a query embedding.

Refer to `embed.py` and `populate_supabase.py` (if available) or Supabase documentation for details on setting up the database schema and data.