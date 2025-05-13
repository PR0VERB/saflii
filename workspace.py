import uuid
import logging
import json
import html # Added for escaping
from collections import defaultdict # Import defaultdict
from fastapi import APIRouter, Request, Form, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from supabase import Client # Import Supabase client type hint
from postgrest.exceptions import APIError # Import Postgrest APIError for specific DB errors
from auth import get_supabase_client # Import the dependency function

# Assuming templates and logger are initialized in api.py and imported
# from api import templates, logger # Adjust import based on final structure
# For now, let's assume they are passed or globally available for simplicity in this step
# We will properly import them in the final api.py structure

# --- Workspace is now database-driven ---

# --- Pydantic Models ---
# Removed old WorkspaceItem model, no longer needed for session storage
class ReorderItemsPayload(BaseModel):
    ordered_ids: list[str] # Expecting a list of project_item UUIDs (as strings)

# --- Router Setup ---
router = APIRouter()
# Placeholder for logger - will be properly imported from api.py later
logger = logging.getLogger(__name__)
# Placeholder for templates - will be properly imported from api.py later
# This requires templates to be initialized before this module is imported in api.py
# A better approach might be dependency injection if complexity grows.
from api import templates # Assuming api.py initializes templates

# --- Workspace Endpoints ---

@router.get("/workspace/", response_class=HTMLResponse)
async def view_workspace(request: Request, db: Client = Depends(get_supabase_client)):
    """Displays the workspace page with user's projects."""
    logger.info("--- view_workspace: Request received ---")
    user = request.session.get('user')

    if not user or not user.get('id'):
        logger.warning("view_workspace: User not logged in or user ID missing in session. Redirecting to login.")
        # Redirect to login if user is not authenticated
        return RedirectResponse(url="/login", status_code=303) # Use 303 for GET redirect

    user_id = user['id']
    logger.info(f"view_workspace: User {user.get('email')} (ID: {user_id}) authenticated.")

    try:
        # Fetch projects for the logged-in user
        logger.info(f"view_workspace: Fetching projects for user_id: {user_id}")
        project_response = db.table('projects').select('*').eq('user_id', user_id).order('created_at', desc=False).execute()
        projects = project_response.data
        logger.info(f"view_workspace: Found {len(projects)} projects for user {user_id}.")
        logger.debug(f"view_workspace: Projects data: {json.dumps(projects, indent=2)}")

        # TODO: Fetch project item counts later if needed for display

        logger.info("view_workspace: Rendering workspace.html template...")
        response = templates.TemplateResponse("workspace.html", {
            "request": request,
            "projects": projects,
            "user": user,
            # Add other context needed by the template (e.g., workspace_count might be project count now)
            "workspace_count": len(projects) # Example: count is now number of projects
        })
        logger.info("--- view_workspace: Request finished ---")
        return response

    except Exception as e:
        logger.error(f"Error loading workspace page for user {user_id}: {e}", exc_info=True)
        # Consider a more user-friendly error page/message
        # For now, re-raise or return a generic error response
        # Re-raising might be caught by a global exception handler if you have one
        # raise HTTPException(status_code=500, detail="Could not load workspace projects.")
        # Or return an error template/response:
        return templates.TemplateResponse("error.html", {"request": request, "detail": "Could not load your workspace projects."}, status_code=500) # Assuming you have an error.html

# --- Endpoint to Create a New Project ---
@router.post("/projects/create", response_class=HTMLResponse)
async def create_project(
    request: Request,
    project_name: str = Form(...),
    project_description: str = Form(None), # Optional description
    db: Client = Depends(get_supabase_client)
):
    """Handles creation of a new project."""
    logger.info("--- create_project: Request received ---")
    user = request.session.get('user')

    if not user or not user.get('id'):
        logger.warning("create_project: User not logged in or user ID missing. Cannot create project.")
        # Return an error response suitable for HTMX
        return HTMLResponse("<div class='message message-error'>Authentication required to create projects. Please log in.</div>", status_code=401)

    user_id = user['id']
    logger.info(f"create_project: Attempting to create project '{project_name}' for user_id: {user_id}")

    if not project_name or len(project_name.strip()) == 0:
         logger.warning("create_project: Project name is empty.")
         # Return error message within the form area (assuming HTMX target)
         return HTMLResponse("<div class='message message-error'>Project name cannot be empty.</div>", status_code=400)


    try:
        # Insert the new project into the database
        insert_data = {
            "user_id": user_id,
            "name": project_name.strip(),
            "description": project_description.strip() if project_description else None
        }
        logger.debug(f"create_project: Inserting data: {insert_data}")
        project_response = db.table('projects').insert(insert_data).execute()

        # Check for errors during insertion (e.g., duplicate name)
        if project_response.data:
            new_project = project_response.data[0]
            logger.info(f"create_project: Successfully created project ID {new_project['id']} for user {user_id}.")
            # Return the newly created project item to be appended to the list via HTMX
            # We need a partial template for a single project row/card
            # For now, let's just return a success message and trigger a page reload/swap
            # Ideally, return the HTML fragment for the new project:
            # return templates.TemplateResponse("partials/project_item.html", {"request": request, "project": new_project})
            # Return success message in the form area and trigger sidebar refresh via header
            success_message_html = f"<div id='create-project-message' class='message message-success'>Project '{new_project['name']}' created successfully.</div>"
            # Create a standard Response to set headers
            response = Response(content=success_message_html, status_code=201, media_type="text/html")
            response.headers["HX-Trigger"] = "projectListChanged" # Trigger the custom event
            logger.info("create_project: Returning success message and HX-Trigger header.")
            return response
        else:
            # Handle potential insertion errors (like unique constraint violation)
            # Supabase might return an error in the response or raise an exception depending on client version/config
            error_detail = "Could not create project. It might already exist or there was a server error."
            # Attempt to get more specific error if available (this part might need adjustment)
            # if hasattr(project_response, 'error') and project_response.error:
            #    logger.error(f"create_project: Supabase insert error: {project_response.error}")
            #    if "unique constraint" in str(project_response.error):
            #         error_detail = f"Project with name '{project_name}' already exists."

            logger.error(f"create_project: Failed to insert project for user {user_id}. Response: {project_response}")
            return HTMLResponse(f"<div id='create-project-message' class='message message-error'>{error_detail}</div>", status_code=400) # Bad Request or Conflict (409) might be better

    except Exception as e:
        logger.error(f"Error creating project for user {user_id}: {e}", exc_info=True)
        return HTMLResponse("<div id='create-project-message' class='message message-error'>An unexpected error occurred while creating the project.</div>", status_code=500)


# --- Endpoint to Reload Project List for Sidebar ---
@router.get("/workspace/sidebar_projects", response_class=HTMLResponse)
async def get_sidebar_projects_list(
    request: Request,
    current_project_id: str | None = Query(None), # Optional query param to highlight active project
    db: Client = Depends(get_supabase_client)
):
    """Returns the HTML fragment for the list of projects formatted for the sidebar."""
    logger.info(f"--- get_sidebar_projects_list: Request received (current_project_id: {current_project_id}) ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        # Don't return error message here, just empty list or placeholder in template
        logger.warning("get_sidebar_projects_list: User not logged in.")
        return templates.TemplateResponse("partials/sidebar_project_list.html", {
            "request": request,
            "projects": [],
            "current_project_id": current_project_id
        })

    user_id = user['id']
    try:
        # Fetch only id and name, ordered by name for the sidebar list
        project_response = db.table('projects').select('id, name, description').eq('user_id', user_id).order('name', desc=False).execute()
        projects = project_response.data
        logger.info(f"get_sidebar_projects_list: Found {len(projects)} projects for user {user_id}.")
        # Render the new partial template for the sidebar
        return templates.TemplateResponse("partials/sidebar_project_list.html", {
            "request": request,
            "projects": projects,
            "current_project_id": current_project_id # Pass this for highlighting
        })
    except Exception as e:
        logger.error(f"Error fetching sidebar project list fragment for user {user_id}: {e}", exc_info=True)
        # Return an empty list representation in case of error
        return templates.TemplateResponse("partials/sidebar_project_list.html", {
            "request": request,
            "projects": [],
            "current_project_id": current_project_id,
             "error": "Could not load projects" # Optional error message for template
        })
# --- Endpoint to get the form for adding an item to a project ---
@router.get("/workspace/get_add_to_project_form/{paragraph_id}", response_class=HTMLResponse)
async def get_add_to_project_form(
    request: Request,
    paragraph_id: str, # Changed type hint to str to match search result ID type
    user_query: str | None = None, # Add query parameter
    db: Client = Depends(get_supabase_client)
):
    """Fetches user's projects and returns the 'Add to Project' form."""
    print(f"[DEBUG] get_add_to_project_form: Route hit.") # DEBUG LOG
    print(f"[DEBUG] get_add_to_project_form: Received paragraph_id: {paragraph_id}") # DEBUG LOG
    print(f"[DEBUG] get_add_to_project_form: Received user_query: {user_query}") # DEBUG LOG
    logger.info(f"--- get_add_to_project_form: Request received for paragraph_id: {paragraph_id}, query: '{user_query}' ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("get_add_to_project_form: User not logged in.")
        # Return an inline error message instead of triggering a toast
        error_html = "<span class='message message-error' style='font-size: 0.9em; padding: 2px 5px;'>Login required or session expired. Please refresh and log in.</span>"
        # Return 401 Unauthorized status code along with the inline message
        return HTMLResponse(content=error_html, status_code=401)

    user_id = user['id']
    logger.info(f"get_add_to_project_form: Fetching projects for user_id: {user_id}")

    try:
        # Fetch IDs of projects this paragraph already belongs to for this user
        existing_projects_response = db.table('project_items').select(
            'project_id' # Only need the project ID
        ).eq('paragraph_id', paragraph_id).execute() # We'll filter by user ownership when fetching all projects

        existing_project_ids = {item['project_id'] for item in existing_projects_response.data} if existing_projects_response.data else set()
        logger.info(f"get_add_to_project_form: Paragraph {paragraph_id} is already in projects: {existing_project_ids} (checking against user's projects).")

        # Always fetch all user's projects for the dropdown
        logger.info(f"get_add_to_project_form: Fetching all projects for user {user_id} for the form.")
            # Fetch user's projects if item doesn't exist
        project_response = db.table('projects').select('id, name').eq('user_id', user_id).order('name').execute()
        all_user_projects = project_response.data
        logger.info(f"get_add_to_project_form: Found {len(all_user_projects)} total projects for user {user_id}.")

        # Filter out projects the user doesn't own from the existing_project_ids set for safety, though the query below does the main filtering
        user_project_ids = {p['id'] for p in all_user_projects}
        relevant_existing_project_ids = existing_project_ids.intersection(user_project_ids)
        logger.info(f"get_add_to_project_form: Paragraph {paragraph_id} is already in user's projects: {relevant_existing_project_ids}.")

        # Render the partial template containing the form
        print(f"[DEBUG] get_add_to_project_form: Rendering template partials/add_to_project_form.html") # DEBUG LOG
        return templates.TemplateResponse("partials/add_to_project_form.html", {
            "request": request,
            "projects": all_user_projects,
            "paragraph_id": paragraph_id,
            "user_query": user_query or "", # Pass query to template
            "existing_project_ids": relevant_existing_project_ids # Pass the set of IDs where the item already exists
            })

    except Exception as e:
        logger.error(f"Error fetching projects for add form (user: {user_id}, paragraph: {paragraph_id}): {e}", exc_info=True)
        # Return an error message within the target div
        return HTMLResponse(f"<div class='message message-error'>Error loading projects. Cannot add item.</div>", status_code=500)


# --- Endpoint to handle adding an item to a project ---
@router.post("/project_items/add", response_class=HTMLResponse)
async def add_item_to_project(
    request: Request,
    paragraph_id: str = Form(...), # Changed type hint to str to match search result ID type
    project_id: str = Form(...), # Expecting project UUID
    user_query: str = Form(""), # Get the query from the hidden input, default to empty string
    comment: str = Form(None), # Add optional comment field
    db: Client = Depends(get_supabase_client)
):
    """Adds a paragraph (item) to a specified project."""
    print(f"--- [DEBUG] add_item_to_project: Request received ---") # DEBUG LOG
    logger.info(f"--- add_item_to_project: Request received ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("add_item_to_project: User not logged in. Triggering redirect to signup.")
        # Return an empty response with HX-Redirect header
        response = Response(status_code=401) # Use 401 Unauthorized
        response.headers["HX-Redirect"] = "/signup.html"
        return response

    user_id = user['id']
    print(f"[DEBUG] add_item_to_project: User {user_id} attempting to add paragraph {paragraph_id} to project {project_id} (Query: '{user_query}', Comment: '{comment}')") # DEBUG LOG
    logger.info(f"add_item_to_project: User {user_id} attempting to add paragraph {paragraph_id} to project {project_id} (Query: '{user_query}')")

    # Input Validation
    if not project_id:
         return HTMLResponse("<div class='message message-error'>No project selected.</div>", status_code=400)
    if not paragraph_id:
         return HTMLResponse("<div class='message message-error'>Invalid item ID.</div>", status_code=400)

    # TODO: Handle 'Create New Project' case if implemented in the form

    try:
        # Verify the selected project belongs to the user before inserting
        print(f"[DEBUG] add_item_to_project: Checking if user {user_id} owns project {project_id}") # DEBUG LOG
        project_check = db.table('projects').select('id').eq('id', project_id).eq('user_id', user_id).maybe_single().execute()

        print(f"[DEBUG] add_item_to_project: Project ownership check result: {project_check.data}") # DEBUG LOG
        if not project_check.data:
            logger.warning(f"add_item_to_project: User {user_id} attempted to add to project {project_id} they don't own or doesn't exist.")
            return HTMLResponse("<div class='message message-error'>Invalid project selected or permission denied.</div>", status_code=403) # Forbidden

        # Insert the link into project_items
        insert_data = {
            "project_id": project_id,
            "paragraph_id": paragraph_id,
            "search_query": user_query, # Add the search query
            "comment": comment.strip() if comment else None, # Include the comment if provided
            # user_id is implicitly checked via project ownership
        }
        print(f"[DEBUG] add_item_to_project: Preparing insert data: {insert_data}") # DEBUG LOG
        logger.debug(f"add_item_to_project: Inserting into project_items: {insert_data}")
        try:
            print(f"[DEBUG] add_item_to_project: Attempting database insert...") # DEBUG LOG
            item_response = db.table('project_items').insert(insert_data).execute()
        except APIError as db_error: # Catch specific database API errors during execute()
            print(f"[DEBUG] add_item_to_project: Database APIError occurred: {db_error}") # DEBUG LOG
            logger.error(f"Database APIError adding item to project (User: {user_id}, Project: {project_id}, Paragraph: {paragraph_id}): {db_error}", exc_info=True)
            # Return the specific HTML snippet requested for database errors
            error_html = "<span class=\"text-danger\">Error adding item. Please try again.</span>"
            # Optionally trigger a toast as well for consistency
            toast_event = json.dumps({"showToast": {"message": "Database error occurred.", "type": "error"}})
            response = Response(content=error_html, status_code=500, media_type="text/html")
            response.headers["HX-Trigger"] = toast_event
            return response
        except Exception as db_exec_error: # Catch other potential errors during execute()
             print(f"[DEBUG] add_item_to_project: Unexpected error during DB insert execution: {db_exec_error}") # DEBUG LOG
             logger.error(f"Unexpected error during database insert execution (User: {user_id}, Project: {project_id}, Paragraph: {paragraph_id}): {db_exec_error}", exc_info=True)
             error_html = "<span class=\"text-danger\">Error adding item. Please try again.</span>"
             toast_event = json.dumps({"showToast": {"message": "An unexpected database error occurred.", "type": "error"}})
             response = Response(content=error_html, status_code=500, media_type="text/html")
             response.headers["HX-Trigger"] = toast_event
             return response

        # Check Supabase response *after* successful execution
        if item_response.data:
            print(f"[DEBUG] add_item_to_project: Database insert successful. Response data: {item_response.data}") # DEBUG LOG
            logger.info(f"add_item_to_project: Successfully added paragraph {paragraph_id} to project {project_id} for user {user_id}.")
            # Return a success message and trigger a success toast
            response_html = "<span class='message message-success' style='font-size: 0.9em; padding: 2px 5px;'>Added!</span>" # Changed class and text
            toast_event = json.dumps({"showToast": {"message": "Item added to project!", "type": "success"}})
            response = Response(content=response_html, media_type="text/html")
            response.headers["HX-Trigger"] = toast_event
            return response
        else:
            # Handle potential insertion errors reported by Supabase (like unique constraint violation)
            error_detail = "Could not add item. It might already be in this project."
            # Check specific Supabase errors if possible
            # if hasattr(item_response, 'error') and item_response.error and "unique constraint" in str(item_response.error):
            #    error_detail = "This item is already in the selected project."

            print(f"[DEBUG] add_item_to_project: Database insert failed (no data in response). Response: {item_response}") # DEBUG LOG
            logger.error(f"add_item_to_project: Failed to insert item (Supabase response indicated failure). User: {user_id}, Project: {project_id}, Paragraph: {paragraph_id}. Response: {item_response}")
            # Return error message in the form area and trigger an error toast
            response_html = f"<div class='message message-error'>{error_detail}</div>"
            toast_event = json.dumps({"showToast": {"message": error_detail, "type": "error"}})
            response = Response(content=response_html, status_code=400, media_type="text/html")
            response.headers["HX-Trigger"] = toast_event
            return response

    except Exception as e:
        print(f"[DEBUG] add_item_to_project: General exception caught: {e}") # DEBUG LOG
        logger.error(f"Error adding item to project (User: {user_id}, Project: {project_id}, Paragraph: {paragraph_id}): {e}", exc_info=True)
        # Return error message in the form area and trigger an error toast
        error_message = "An unexpected error occurred."
        response_html = f"<div class='message message-error'>{error_message}</div>"
        toast_event = json.dumps({"showToast": {"message": error_message, "type": "error"}})
        response = Response(content=response_html, status_code=500, media_type="text/html")
        response.headers["HX-Trigger"] = toast_event
        return response
# --- Endpoint to fetch and display items within a specific project ---
@router.get("/projects/{project_id}/items", response_class=HTMLResponse)
async def get_project_items(
    request: Request,
    project_id: str, # Project UUID
    db: Client = Depends(get_supabase_client)
):
    """Fetches and returns the list of items (paragraphs) for a given project."""
    logger.info(f"--- get_project_items: Request received for project_id: {project_id} ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("get_project_items: User not logged in.")
        return HTMLResponse("<div>Authentication required to view project items.</div>", status_code=401)

    user_id = user['id']
    logger.info(f"get_project_items: User {user_id} requesting items for project {project_id}")

    try:
        # 1. Verify user owns the project
        project_check = db.table('projects').select('id, name').eq('id', project_id).eq('user_id', user_id).maybe_single().execute()
        if not project_check.data:
            logger.warning(f"get_project_items: Project {project_id} not found or not owned by user {user_id}.")
            return HTMLResponse("<div>Project not found or access denied.</div>", status_code=404) # Or 403

        project_name = project_check.data['name']
        logger.info(f"get_project_items: Project '{project_name}' verified for user {user_id}.")

        # 2. Fetch items associated with the project, joining with saflii_cases
        # Assumes 'saflii_cases' is the correct table name referenced by 'paragraph_id' FK
        # The select query fetches all columns from project_items (*) and specified columns from the related saflii_cases table
        items_response = db.table('project_items').select(
            'id, added_at, paragraph_id, search_query, comment, saflii_cases(id, filename, paragraph, htmlsaflii)' # Added comment
        ).eq('project_id', project_id).order('display_order', desc=False).order('added_at', desc=True).execute() # Order by display_order first, then added_at

        project_items_with_details = items_response.data
        logger.info(f"get_project_items: Found {len(project_items_with_details)} items for project {project_id}.")
        logger.debug(f"get_project_items: Items data: {json.dumps(project_items_with_details, indent=2)}")


        # 3. Render the partial template with the fetched items
        return templates.TemplateResponse("partials/project_item_list.html", {
            "request": request,
            "items_in_group": project_items_with_details, # Changed 'items' to 'items_in_group' to match template
            "project_id": project_id,
            "project_name": project_name
        })

    except Exception as e:
        logger.error(f"Error fetching items for project {project_id} (User: {user_id}): {e}", exc_info=True)
        return HTMLResponse(f"<div class='message message-error'>Error loading items for project.</div>", status_code=500)


# --- Endpoint to remove an item from a project ---
@router.delete("/project_items/{project_item_id}", response_class=HTMLResponse)
async def remove_item_from_project(
    request: Request,
    project_item_id: str, # This is the ID from the project_items table
    db: Client = Depends(get_supabase_client)
):
    """Removes a specific item entry from the project_items table."""
    logger.info(f"--- remove_item_from_project: Request received for project_item_id: {project_item_id} ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("remove_item_from_project: User not logged in.")
        # Although the query checks ownership, good to block early
        return HTMLResponse("", status_code=401) # Return empty on auth error

    user_id = user['id']
    logger.info(f"remove_item_from_project: User {user_id} attempting to remove item {project_item_id}")

    try:
        # Delete the item, ensuring it belongs to a project owned by the user
        # We join project_items with projects to check ownership before deleting
        # This is slightly complex for a direct delete, an alternative is to fetch first, then delete.
        # Let's use the simpler fetch-then-delete approach for clarity.

        # 1. Fetch the project_item and the associated project_id
        item_check = db.table('project_items').select('id, project_id, projects(user_id)').eq('id', project_item_id).maybe_single().execute()

        if not item_check.data:
            logger.warning(f"remove_item_from_project: Item {project_item_id} not found.")
            return HTMLResponse("", status_code=404) # Not Found

        # 2. Check ownership via the nested project data
        if not item_check.data.get('projects') or item_check.data['projects']['user_id'] != user_id:
            logger.warning(f"remove_item_from_project: User {user_id} does not own the project containing item {project_item_id}.")
            return HTMLResponse("", status_code=403) # Forbidden

        # 3. Delete the item
        delete_response = db.table('project_items').delete().eq('id', project_item_id).execute()

        # Check if deletion was successful (usually based on count or lack of error)
        # Supabase delete response structure might vary, check documentation if needed
        # Assuming success if no exception is raised and potentially checking response count if available
        # if delete_response.count > 0: # Example check
        logger.info(f"remove_item_from_project: Successfully removed item {project_item_id} for user {user_id}.")
        # Return empty response (to remove item via outerHTML swap) and trigger success toast
        toast_event = json.dumps({"showToast": {"message": "Item removed from project.", "type": "success"}})
        response = Response(content="", media_type="text/html")
        response.headers["HX-Trigger"] = toast_event
        return response
        # else:
        #    logger.error(f"remove_item_from_project: Failed to delete item {project_item_id} despite checks. Response: {delete_response}")
        #    return HTMLResponse("<div class='message message-error'>Failed to remove item.</div>", status_code=500)


    except Exception as e:
        logger.error(f"Error removing item {project_item_id} (User: {user_id}): {e}", exc_info=True)
        # Return empty response but trigger an error toast
        error_message = "Failed to remove item."
        toast_event = json.dumps({"showToast": {"message": error_message, "type": "error"}})
        response = Response(content="", status_code=500, media_type="text/html")
        response.headers["HX-Trigger"] = toast_event
        return response


# --- Endpoint to Update a Comment on a Project Item ---
@router.post("/project_items/{project_item_id}/comment", response_class=HTMLResponse)
async def update_project_item_comment(
    request: Request,
    project_item_id: str, # The ID from the project_items table
    comment: str = Form(...), # The new comment text from the form
    db: Client = Depends(get_supabase_client)
):
    """Updates the comment for a specific project item."""
    logger.info(f"--- update_project_item_comment: Request received for project_item_id: {project_item_id} ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("update_project_item_comment: User not logged in.")
        # Return an error message suitable for HTMX swap
        return HTMLResponse("<span class='message message-error'>Authentication required.</span>", status_code=401)

    user_id = user['id']
    new_comment = comment.strip() # Clean whitespace
    logger.info(f"update_project_item_comment: User {user_id} attempting to update comment for item {project_item_id} to: '{new_comment[:50]}...'") # Log truncated comment

    try:
        # 1. Fetch the project_item and verify ownership (similar to remove logic)
        item_check = db.table('project_items').select('id, project_id, projects(user_id)').eq('id', project_item_id).maybe_single().execute()

        if not item_check.data:
            logger.warning(f"update_project_item_comment: Item {project_item_id} not found.")
            return HTMLResponse("<span class='message message-error'>Item not found.</span>", status_code=404)

        # 2. Check ownership via the nested project data
        if not item_check.data.get('projects') or item_check.data['projects']['user_id'] != user_id:
            logger.warning(f"update_project_item_comment: User {user_id} does not own the project containing item {project_item_id}.")
            return HTMLResponse("<span class='message message-error'>Permission denied.</span>", status_code=403)

        # 3. Update the comment
        update_response = db.table('project_items').update({'comment': new_comment}).eq('id', project_item_id).execute()

        logger.info(f"update_project_item_comment: Successfully updated comment for item {project_item_id} for user {user_id}.")

        # Escape the comment for safe HTML embedding
        escaped_comment = html.escape(new_comment)
        original_escaped_comment_for_error = html.escape(comment) # Escape original input for error case

        # Construct the HTML for the display view
        # Construct the HTML for the display view separately to handle f-string nesting
        if new_comment:
            comment_content_html = f'<p style="margin-bottom: 0.25rem;"><span class="item-comment-text">{escaped_comment}</span></p>'
        else:
            comment_content_html = '<p style="margin-bottom: 0.25rem; font-style: italic; color: var(--text-secondary);">No comment added.</p>'

        edit_button_text = 'Edit' if new_comment else 'Add'

        comment_display_html = f"""
        <div class="comment-display-view-{project_item_id}">
            {comment_content_html}
            <button type="button" class="button button-secondary button-small" style="padding: 0.1rem 0.3rem; font-size: 0.75em;"
                    onclick="document.querySelector('.comment-display-view-{project_item_id}').style.display='none'; document.querySelector('.comment-edit-form-{project_item_id}').style.display='block';">
                {edit_button_text} Comment
            </button>
        </div>
        """
        # Construct the HTML for the hidden edit form
        comment_edit_form_html = f"""
        <form class="comment-edit-form-{project_item_id}" style="display: none; margin-top: 0.5rem;"
              hx-post="/project_items/{project_item_id}/comment"
              hx-target="#comment-section-{project_item_id}"
              hx-swap="innerHTML">
            <textarea name="comment" rows="3" style="width: 100%; margin-bottom: 0.5rem; font-size: 0.9em; padding: 0.3rem;"
                      placeholder="Enter your comment...">{escaped_comment}</textarea>
            <div style="display: flex; gap: 0.5rem;">
                <button type="submit" class="button button-primary button-small" style="padding: 0.2rem 0.4rem; font-size: 0.8em;">
                    Save Comment
                </button>
                <button type="button" class="button button-secondary button-small" style="padding: 0.2rem 0.4rem; font-size: 0.8em;"
                        onclick="document.querySelector('.comment-edit-form-{project_item_id}').style.display='none'; document.querySelector('.comment-display-view-{project_item_id}').style.display='block';">
                    Cancel
                </button>
            </div>
        </form>
        """
        # Combine both parts for the final response
        final_html_response = comment_display_html + comment_edit_form_html
        return HTMLResponse(content=final_html_response)

    except APIError as db_error: # Restored except block
        logger.error(f"Database APIError updating comment for item {project_item_id} (User: {user_id}): {db_error}", exc_info=True)
        # Construct error HTML piece by piece to avoid f-string issues
        error_html = f'<div class="comment-display-view-{project_item_id}">'
        error_html += '<p style="margin-bottom: 0.25rem;"><span class="message message-error">Database error updating comment.</span></p>'
        error_html += f'<button type="button" class="button button-secondary button-small" style="padding: 0.1rem 0.3rem; font-size: 0.75em;" '
        # Carefully construct onclick JS string
        onclick_js_display = f"document.querySelector('.comment-display-view-{project_item_id}').style.display='none'; document.querySelector('.comment-edit-form-{project_item_id}').style.display='block';"
        error_html += f'onclick="{html.escape(onclick_js_display)}">' # Escape JS for HTML attribute
        error_html += 'Retry Edit</button></div>' # Close display view div

        error_html += f'<form class="comment-edit-form-{project_item_id}" style="display: none; margin-top: 0.5rem;" '
        error_html += f'hx-post="/project_items/{project_item_id}/comment" '
        error_html += f'hx-target="#comment-section-{project_item_id}" hx-swap="innerHTML">'
        error_html += f'<textarea name="comment" rows="3" style="width: 100%; margin-bottom: 0.5rem; font-size: 0.9em; padding: 0.3rem;" placeholder="Enter your comment...">{original_escaped_comment_for_error}</textarea>'
        error_html += '<div style="display: flex; gap: 0.5rem;">'
        error_html += '<button type="submit" class="button button-primary button-small" style="padding: 0.2rem 0.4rem; font-size: 0.8em;">Save Comment</button>'
        error_html += f'<button type="button" class="button button-secondary button-small" style="padding: 0.2rem 0.4rem; font-size: 0.8em;" '
        # Carefully construct onclick JS string for cancel
        onclick_js_cancel = f"document.querySelector('.comment-edit-form-{project_item_id}').style.display='none'; document.querySelector('.comment-display-view-{project_item_id}').style.display='block';"
        error_html += f'onclick="{html.escape(onclick_js_cancel)}">' # Escape JS for HTML attribute
        error_html += 'Cancel</button></div></form>' # Close div and form
        return HTMLResponse(content=error_html, status_code=500)

    except Exception as e: # Restored except block
        logger.error(f"Error updating comment for item {project_item_id} (User: {user_id}): {e}", exc_info=True)
        # Construct error HTML piece by piece
        error_html = f'<div class="comment-display-view-{project_item_id}">'
        error_html += '<p style="margin-bottom: 0.25rem;"><span class="message message-error">Server error updating comment.</span></p>'
        error_html += f'<button type="button" class="button button-secondary button-small" style="padding: 0.1rem 0.3rem; font-size: 0.75em;" '
        # Carefully construct onclick JS string
        onclick_js_display = f"document.querySelector('.comment-display-view-{project_item_id}').style.display='none'; document.querySelector('.comment-edit-form-{project_item_id}').style.display='block';"
        error_html += f'onclick="{html.escape(onclick_js_display)}">' # Escape JS for HTML attribute
        error_html += 'Retry Edit</button></div>' # Close display view div

        error_html += f'<form class="comment-edit-form-{project_item_id}" style="display: none; margin-top: 0.5rem;" '
        error_html += f'hx-post="/project_items/{project_item_id}/comment" '
        error_html += f'hx-target="#comment-section-{project_item_id}" hx-swap="innerHTML">'
        error_html += f'<textarea name="comment" rows="3" style="width: 100%; margin-bottom: 0.5rem; font-size: 0.9em; padding: 0.3rem;" placeholder="Enter your comment...">{original_escaped_comment_for_error}</textarea>'
        error_html += '<div style="display: flex; gap: 0.5rem;">'
        error_html += '<button type="submit" class="button button-primary button-small" style="padding: 0.2rem 0.4rem; font-size: 0.8em;">Save Comment</button>'
        error_html += f'<button type="button" class="button button-secondary button-small" style="padding: 0.2rem 0.4rem; font-size: 0.8em;" '
        # Carefully construct onclick JS string for cancel
        onclick_js_cancel = f"document.querySelector('.comment-edit-form-{project_item_id}').style.display='none'; document.querySelector('.comment-display-view-{project_item_id}').style.display='block';"
        error_html += f'onclick="{html.escape(onclick_js_cancel)}">' # Escape JS for HTML attribute
        error_html += 'Cancel</button></div></form>' # Close div and form
        return HTMLResponse(content=error_html, status_code=500)


# --- Endpoint to display the dedicated page for a single project ---
@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def view_project_detail(
    request: Request,
    project_id: str, # Project UUID
    db: Client = Depends(get_supabase_client)
):
    """Fetches project details and its items, then renders the dedicated project page."""
    logger.info(f"--- view_project_detail: Request received for project_id: {project_id} ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("view_project_detail: User not logged in. Redirecting to login.")
        return RedirectResponse(url="/login", status_code=303)

    user_id = user['id']
    logger.info(f"view_project_detail: User {user_id} requesting detail page for project {project_id}")

    try:
        # 1. Verify user owns the project and get its details
        project_check = db.table('projects').select('*').eq('id', project_id).eq('user_id', user_id).maybe_single().execute()
        if not project_check.data:
            logger.warning(f"view_project_detail: Project {project_id} not found or not owned by user {user_id}.")
            # Render error page
            return templates.TemplateResponse("error.html", {"request": request, "detail": "Project not found or access denied."}, status_code=404)

        project_details = project_check.data
        logger.info(f"view_project_detail: Project '{project_details['name']}' verified for user {user_id}.")

        # 2. Fetch items associated with the project (same logic as get_project_items)
        items_response = db.table('project_items').select(
            'id, added_at, paragraph_id, search_query, comment, saflii_cases(id, filename, paragraph, htmlsaflii)' # Added comment back
        ).eq('project_id', project_id).order('display_order', desc=False).order('added_at', desc=True).execute() # Order by display_order first, then added_at

        project_items_with_details = items_response.data
        logger.info(f"view_project_detail: Found {len(project_items_with_details)} items for project {project_id}.")

        # 3. Group items by search query
        grouped_items = defaultdict(list)
        for item in project_items_with_details:
            query = item.get('search_query') or "No Associated Query" # Handle null/empty queries
            grouped_items[query].append(item)
        logger.debug(f"view_project_detail: Grouped items: {json.dumps(grouped_items, indent=2)}")


        # 4. Fetch project count for the sidebar badge
        count_response = db.table('projects').select('id', count='exact').eq('user_id', user_id).execute()
        workspace_count = count_response.count if count_response.count is not None else 0
        logger.info(f"view_project_detail: Fetched workspace_count: {workspace_count} for user {user_id}.")


        # 5. Render the full project detail page template with grouped items
        return templates.TemplateResponse("project_detail.html", {
            "request": request,
            "project": project_details,
            "grouped_items": grouped_items, # Pass grouped items instead of flat list
            "user": user, # Pass user for header/nav consistency
            "workspace_count": workspace_count, # Pass count for sidebar badge in base.html
            "current_project_id": project_id # Pass current project ID for sidebar highlighting
        })

    except Exception as e:
        logger.error(f"Error loading project detail page {project_id} (User: {user_id}): {e}", exc_info=True)
        return templates.TemplateResponse("error.html", {"request": request, "detail": "Error loading project details."}, status_code=500)


# --- Endpoint to Export Original HTML Snippet ---
@router.get("/export/html/{paragraph_id}")
async def export_paragraph_html(
    request: Request,
    paragraph_id: int,
    db: Client = Depends(get_supabase_client)
):
    """Exports the original HTML content of a specific paragraph."""
    logger.info(f"--- export_paragraph_html: Request received for paragraph_id: {paragraph_id} ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("export_paragraph_html: User not logged in. Denying export.")
        # Although the data isn't strictly user-owned, prevent anonymous access
        raise HTTPException(status_code=401, detail="Authentication required to export content.")

    user_id = user['id'] # Log which user is exporting
    logger.info(f"export_paragraph_html: User {user_id} requesting export for paragraph {paragraph_id}")

    try:
        # Fetch the specific paragraph data including htmlsaflii
        item_response = db.table('saflii_cases').select('filename, htmlsaflii').eq('id', paragraph_id).maybe_single().execute()

        if not item_response.data or not item_response.data.get('htmlsaflii'):
            logger.warning(f"export_paragraph_html: Paragraph {paragraph_id} not found or HTML content missing.")
            raise HTTPException(status_code=404, detail="HTML content not found for this item.")

        html_content = item_response.data['htmlsaflii']
        original_filename = item_response.data.get('filename', f'paragraph_{paragraph_id}')
        # Sanitize filename slightly and add .html extension
        export_filename = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in original_filename).rstrip('_') + f"_p{paragraph_id}.html"

        logger.info(f"export_paragraph_html: Returning HTML content for paragraph {paragraph_id} as filename '{export_filename}'.")

        # Return HTMLResponse with Content-Disposition header to suggest download
        return HTMLResponse(
            content=html_content,
            headers={
                "Content-Disposition": f'attachment; filename="{export_filename}"'
            }
        )

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions (like 401, 404)
        raise http_exc
    except Exception as e:
        logger.error(f"Error exporting HTML for paragraph {paragraph_id} (User: {user_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not export HTML content due to a server error.")


# --- Endpoint to Reorder Items in a Project ---
@router.post("/api/project_items/reorder") # Changed path to be more API-like
async def reorder_project_items(
    request: Request,
    payload: ReorderItemsPayload, # Use the Pydantic model to parse the body
    db: Client = Depends(get_supabase_client)
):
    """Updates the display order of items within a project."""
    logger.info(f"--- reorder_project_items: Request received ---")
    user = request.session.get('user')
    if not user or not user.get('id'):
        logger.warning("reorder_project_items: User not logged in.")
        raise HTTPException(status_code=401, detail="Authentication required.")

    user_id = user['id']
    ordered_ids = payload.ordered_ids
    logger.info(f"reorder_project_items: User {user_id} attempting to reorder {len(ordered_ids)} items.")
    logger.debug(f"reorder_project_items: Received order: {ordered_ids}")

    if not ordered_ids:
        logger.info("reorder_project_items: No item IDs provided.")
        return {"status": "success", "message": "No items to reorder."} # Or maybe a 400 error?

    try:
        # IMPORTANT: Verify ownership before updating.
        # Fetch all items being reordered to check they belong to the user.
        # This is less efficient than updating directly with a WHERE clause including user_id,
        # but Supabase client might make complex updates tricky. Fetching first is safer.

        # Select items and their project's user_id
        items_check = db.table('project_items').select('id, projects(user_id)').in_('id', ordered_ids).execute()

        if not items_check.data:
             logger.warning(f"reorder_project_items: None of the provided item IDs found: {ordered_ids}")
             raise HTTPException(status_code=404, detail="No valid items found to reorder.")

        # Check if all fetched items belong to the current user
        valid_items_to_update = []
        for item in items_check.data:
            # Ensure 'projects' key exists and 'user_id' matches
            if item.get('projects') and item['projects'].get('user_id') == user_id:
                 valid_items_to_update.append(item['id'])
            else:
                logger.warning(f"reorder_project_items: User {user_id} attempted to reorder item {item['id']} they don't own.")
                # Decide whether to fail the whole request or just skip unauthorized items.
                # Failing whole request is safer.
                raise HTTPException(status_code=403, detail=f"Permission denied for item ID {item['id']}.")

        # Proceed with updates only for verified items in the requested order
        logger.info(f"reorder_project_items: Verified ownership for {len(valid_items_to_update)} items. Proceeding with updates.")

        update_errors = []
        # Update items one by one (less ideal than a transaction, but simpler with current client)
        for index, item_id in enumerate(ordered_ids):
             if item_id in valid_items_to_update: # Ensure we only update verified items
                try:
                    db.table('project_items').update({'display_order': index}).eq('id', item_id).execute()
                    logger.debug(f"reorder_project_items: Updated item {item_id} to display_order {index}")
                except Exception as update_e:
                    logger.error(f"reorder_project_items: Failed to update item {item_id}: {update_e}", exc_info=True)
                    update_errors.append(item_id)

        if update_errors:
             # Decide how to report partial failure
             logger.error(f"reorder_project_items: Failed to update order for items: {update_errors}")
             # Return a 500 error, as the state might be inconsistent
             raise HTTPException(status_code=500, detail=f"Failed to update order for some items: {update_errors}")

        logger.info(f"reorder_project_items: Successfully updated order for {len(ordered_ids)} items.")
        return {"status": "success", "message": "Item order updated successfully."}

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions (like 401, 403, 404)
        raise http_exc
    except Exception as e:
        # Log the specific exception before raising the generic HTTP 500
        logger.exception(f"Unexpected error during item reorder for user {user_id}: {e}") # Use logger.exception to include traceback
        raise HTTPException(status_code=500, detail="An unexpected server error occurred while reordering items.")


# Removed old preview_item endpoint
# Removed old remove_from_workspace endpoint
# Removed old add_to_workspace endpoint
