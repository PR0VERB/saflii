import logging
from fastapi import APIRouter, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from gotrue.types import UserAttributes # Import UserAttributes for update

# Assuming templates is initialized in api.py
# A better approach might be dependency injection if complexity grows.
from api import templates
from supabase import Client, create_client
from gotrue.errors import AuthApiError # Import specific Supabase auth error
import os
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Supabase Client (Re-initialize or pass from api.py/dependency injection) ---
# For simplicity here, we re-initialize. Consider a shared client instance.
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    logger.error("Supabase credentials not found in environment for auth.py.")
    # Handle error appropriately - maybe raise exception or disable auth routes
    supabase: Client | None = None
else:
    try:
        supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        logger.info("Supabase client created for auth.")
    except Exception as e:
        logger.error(f"Failed to create Supabase client for auth: {e}", exc_info=True)
        supabase = None

# --- Helper Function to get Supabase client ---
# This helps manage the potentially None client
async def get_supabase_client() -> Client:
    if supabase is None:
        logger.error("Supabase client is not available.")
        raise HTTPException(status_code=500, detail="Authentication service unavailable.")
    return supabase

# --- Helper Function to get current user from session ---
# This ensures we have a consistent way to check for logged-in users in routes
# And raises an exception if no user is found when one is required.
async def get_current_user(request: Request) -> dict:
    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"HX-Redirect": "/login"}, # Redirect via HTMX if applicable
        )
    # Ensure the user object is a dictionary
    if isinstance(user, str):
        try:
            user = json.loads(user)
        except json.JSONDecodeError:
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid user session data",
            )
    # Add check for user_metadata existence, initialize if missing
    if 'user_metadata' not in user:
        user['user_metadata'] = {}
    return user

# --- Helper Function to update user in session ---
def update_user_session(request: Request, updated_user_data: dict):
    """Updates the user data in the session."""
    request.session['user'] = updated_user_data
    logger.info(f"User session updated for user ID: {updated_user_data.get('id')}")


# --- Routes ---

@router.get("/login", response_class=HTMLResponse, name="login")
async def get_login_page(request: Request):
    """Serves the login page."""
    logger.info("Serving login page.")
    # Add context for base template
    user = request.session.get('user')
    workspace_count = len(request.session.get('workspace', {}))
    return templates.TemplateResponse("login.html", {
        "request": request,
        "user": user,
        "workspace_count": workspace_count
    })

@router.get("/signup", response_class=HTMLResponse, name="signup")
async def get_signup_page(request: Request):
    """Serves the signup page."""
    logger.info("Serving signup page.")
    # Add context for base template
    user = request.session.get('user')
    workspace_count = len(request.session.get('workspace', {}))
    return templates.TemplateResponse("signup.html", {
        "request": request,
        "user": user,
        "workspace_count": workspace_count
    })

@router.post("/login", response_class=HTMLResponse)
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Client = Depends(get_supabase_client)
):
    """Handles user login attempts."""
    logger.info(f"Login attempt for email: {email}")
    try:
        # Use Supabase GoTrueClient for authentication
        response = db.auth.sign_in_with_password({"email": email, "password": password}) # Removed await
        logger.info(f"Supabase login response received for {email}.")
        # Store session info (e.g., access token, user details) in the FastAPI session
        # Convert user object to JSON string (handles datetime) then back to dict for session
        request.session['user'] = json.loads(response.user.json())
        request.session['access_token'] = response.session.access_token # Store token
        logger.info(f"User {email} logged in successfully. Session updated.")

        # Redirect to the main search page upon successful login using HTMX header
        # Alternatively, return a success message to be displayed
        # For HTMX redirects, return 200 OK with the HX-Redirect header
        response = Response(status_code=200)
        response.headers["HX-Redirect"] = "/"
        return response

    except Exception as e:
        logger.error(f"Login failed for {email}: {e}", exc_info=False) # Avoid logging password errors in detail
        # Return the login form with an error message
        # Use status code 401 for unauthorized
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "message": f"Login failed: Invalid email or password.",
                "message_type": "error",
                # Add context for base template
                "user": request.session.get('user'), # Should be None here, but pass anyway
                "workspace_count": len(request.session.get('workspace', {}))
            },
            status_code=401
        )


@router.post("/signup", response_class=HTMLResponse)
async def handle_signup(
    request: Request,
    first_name: str = Form(...), # Added first_name
    surname: str = Form(...),   # Added surname
    email: str = Form(...),
    password: str = Form(...),
    db: Client = Depends(get_supabase_client)
):
    """Handles user signup attempts."""
    logger.info(f"Signup attempt for email: {email}, First Name: {first_name}, Surname: {surname}") # Log new fields
    try:
        # Pass name and surname in the 'data' field within the main credentials dict
        # This data will be stored in user_metadata
        credentials = {
            "email": email,
            "password": password,
            "options": { # Supabase expects metadata under 'options' -> 'data' here
                "data": {
                    "first_name": first_name,
                    "surname": surname
                }
            }
        }
        response = db.auth.sign_up(credentials) # Pass the combined credentials dict
        logger.info(f"Supabase signup response received for {email}.")

        # Check if user object exists and if email confirmation is needed
        if response.user and response.user.identities and not response.user.email_confirmed_at:
             logger.info(f"Signup successful for {email}. Email confirmation required.")
             message = "Signup successful! Please check your email to confirm your account."
             message_type = "success"
        elif response.user:
             logger.info(f"Signup successful for {email}. User already confirmed or confirmation not required.")
             message = "Signup successful! You can now log in."
             message_type = "success"
        # Removed the 'else' block here. If response.user is None after sign_up without an exception,
        # it's an unexpected state, but the generic exception handler below is safer.
        # Specific errors like 'user already exists' are handled via exceptions.

        # Return the signup form with a success/info message
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": message,
                "message_type": message_type,
                # Add context for base template
                "user": request.session.get('user'), # Should be None here
                "workspace_count": len(request.session.get('workspace', {})) # Added missing workspace_count
            }
        )

    except AuthApiError as e:
        error_message = str(e)
        logger.error(f"Supabase Auth API Error during signup for {email}: {error_message}", exc_info=False)

        user_friendly_message = f"Signup failed: {error_message}" # Default
        status_code = 400 # Default Bad Request

        if "User already registered" in error_message:
            user_friendly_message = "Signup failed: An account with this email already exists. Please log in instead."
            status_code = 409 # Conflict
        elif "Password should be at least 6 characters" in error_message:
             user_friendly_message = "Signup failed: Password must be at least 6 characters long."
             status_code = 400 # Bad Request
        elif "Database error saving new user" in error_message:
             user_friendly_message = "Signup failed: Could not create account due to a server issue. Please try again later."
             status_code = 500 # Internal Server Error (reflecting Supabase issue)
        # Add more specific checks if needed

        # Return the signup form with an error message and appropriate status code
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": user_friendly_message,
                "message_type": "error",
                 # Add context for base template
                "user": request.session.get('user'), # Should be None here
                "workspace_count": len(request.session.get('workspace', {}))
            },
             status_code=status_code # Use determined status code
        )
    except Exception as e:
        # Catch-all for other unexpected errors
        logger.error(f"Unexpected error during signup for {email}: {e}", exc_info=True)
        # Correctly structured TemplateResponse call
        return templates.TemplateResponse(
            "signup.html", # Template name
            { # Context dictionary starts
                "request": request,
                "message": "Signup failed: An unexpected error occurred. Please try again later.",
                "message_type": "error",
                "user": request.session.get('user'), # Should be None here
                "workspace_count": len(request.session.get('workspace', {}))
            }, # Context dictionary ends
            status_code=500 # Status code argument *inside* the TemplateResponse call
        )

    except AuthApiError as e:
        error_message = str(e)
        logger.error(f"Supabase Auth API Error during signup for {email}: {error_message}", exc_info=False)
        # Provide specific user-friendly messages for common errors
        if "User already registered" in error_message:
            user_message = "User already registered. Please log in."
            status_code = 409 # Conflict
        elif "Password should be at least 6 characters" in error_message:
             user_message = "Password must be at least 6 characters long."
             status_code = 400 # Bad Request
        else:
            # Generic message for other auth errors
            user_message = "Signup failed due to an authentication issue. Please check your details."
            status_code = 400 # Bad Request
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": user_message,
                "message_type": "error",
                "user": request.session.get('user'),
                "workspace_count": len(request.session.get('workspace', {}))
            },
             status_code=status_code
        )
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error during signup for {email}: {e}", exc_info=True) # Log full traceback for unexpected errors
        # Return the signup form with a generic error message
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "message": "An unexpected error occurred during signup. Please try again later.",
                "message_type": "error",
                "user": request.session.get('user'),
                "workspace_count": len(request.session.get('workspace', {}))
            },
             status_code=500 # Internal Server Error for unexpected issues
        )

@router.post("/logout", name="logout")
async def handle_logout(request: Request, db: Client = Depends(get_supabase_client)):
    """Handles user logout."""
    user_email = request.session.get('user', {}).get('email', 'Unknown user')
    logger.info(f"Logout request received for {user_email}.")
    access_token = request.session.get('access_token')

    if access_token:
        try:
            db.auth.sign_out(access_token) # Removed await
            logger.info(f"Successfully signed out {user_email} from Supabase.")
        except Exception as e:
            logger.error(f"Supabase sign out failed for {user_email}: {e}", exc_info=True)
            # Proceed with clearing local session even if Supabase logout fails

    # Clear user-specific data from the session
    request.session.pop('user', None)
    request.session.pop('access_token', None)
    # Optionally clear the entire workspace too, or keep it associated with the session ID
    # request.session.pop('workspace', None)
    logger.info(f"Local session cleared for {user_email}.")

    # Redirect to homepage
    # Use 200 OK with HX-Redirect for HTMX-driven redirects after POST
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = "/" # Redirect to homepage
    return response


# --- Profile Page ---

@router.get("/profile", response_class=HTMLResponse, name="profile")
async def get_profile_page(request: Request, current_user: dict = Depends(get_current_user)):
    """Serves the user profile page."""
    logger.info(f"Serving profile page for user: {current_user.get('email')}")
    # Ensure user_metadata exists, default name if not present
    user_name = current_user.get('user_metadata', {}).get('name', '')

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": current_user, # Pass the full user object
        "user_name": user_name, # Pass current name for the form
        "workspace_count": len(request.session.get('workspace', {})) # Keep context for base
    })

@router.post("/profile", response_class=HTMLResponse)
async def handle_profile_update(
    request: Request,
    first_name: str = Form(...),
    surname: str = Form(...),
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user) # Get current user data
):
    """Handles updates to the user's profile (e.g., first name, surname)."""
    user_id = current_user.get('id')
    user_email = current_user.get('email')
    access_token = request.session.get('access_token')

    logger.info(f"Profile update attempt for user: {user_email} (ID: {user_id}) with new first name: {first_name}, surname: {surname}")

    if not access_token:
         logger.error(f"Access token not found in session for user {user_email}. Cannot update profile.")
         # Return profile page with error
         return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": current_user,
            "user_name": current_user.get('user_metadata', {}).get('name', ''), # Show old name
            "message": "Authentication error. Please log in again.",
            "message_type": "error",
            "workspace_count": len(request.session.get('workspace', {}))
        }, status_code=status.HTTP_401_UNAUTHORIZED)


    try:
        # Prepare the update data for Supabase
        attributes = UserAttributes(data={'first_name': first_name, 'surname': surname})

        # Update the user's metadata in Supabase
        response = db.auth.update_user(attributes=attributes, jwt=access_token) # Removed await
        logger.info(f"Supabase user update response received for {user_email}.")

        # IMPORTANT: Update the user object in the session immediately
        # The response.user object contains the *updated* user data including metadata
        updated_user_data = json.loads(response.user.json()) # Deserialize the updated user
        update_user_session(request, updated_user_data) # Use helper to update session

        logger.info(f"Profile updated successfully for {user_email}. Session refreshed.")

        # Return the profile page with a success message
        # Pass the *new* name to the template
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": updated_user_data, # Pass updated user data
            "user_name": updated_user_data.get('user_metadata', {}).get('name', ''), # Show new name
            "message": "Profile updated successfully!",
            "message_type": "success",
            "workspace_count": len(request.session.get('workspace', {}))
        })

    except AuthApiError as e:
        logger.error(f"Supabase Auth API Error during profile update for {user_email}: {e}", exc_info=False)
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": current_user, # Show old data on error
            "user_name": current_user.get('user_metadata', {}).get('name', ''),
            "message": f"Profile update failed: {e}",
            "message_type": "error",
            "workspace_count": len(request.session.get('workspace', {}))
        }, status_code=status.HTTP_400_BAD_REQUEST) # Or appropriate error code

    except Exception as e:
        logger.error(f"Unexpected error during profile update for {user_email}: {e}", exc_info=True)
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": current_user, # Show old data on error
            "user_name": current_user.get('user_metadata', {}).get('name', ''),
            "message": f"An unexpected error occurred: {e}",
            "message_type": "error",
            "workspace_count": len(request.session.get('workspace', {}))
        }, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)