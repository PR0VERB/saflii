import uvicorn
import logging
from fastapi import FastAPI, Request # Add Request import
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import secrets # For session secret key
from starlette.middleware.sessions import SessionMiddleware # For session management
# --- Basic Logging Setup ---
# Configure logging centrally here
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Template Setup ---
# Initialize templates centrally
templates = Jinja2Templates(directory="templates")

# --- Helper function to get user from session ---
# This function will be available globally in templates
# --- Helper function get_user_from_request removed (no longer used) ---
# --- Registration of the helper function removed ---

# --- FastAPI App Initialization ---
app = FastAPI(
    title="SAFLII Search & Workspace",
    description="API for searching SAFLII cases and managing a workspace.",
    version="1.0.0"
)

# --- Session Middleware ---
# You MUST set a secret key for session management
# Use a strong, randomly generated key in production and store it securely (e.g., env variable)
SECRET_KEY = secrets.token_hex(32) # Generate a random 32-byte hex key
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    # Optional: configure session cookie parameters (e.g., max_age, path, domain, secure, httponly)
    # max_age=14 * 24 * 60 * 60  # Example: 14 days
)
# --- Mount Static Files ---
# Ensure the 'static' directory exists
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info("Mounted static files directory.")
except RuntimeError:
    logger.warning("Static directory not found or not mountable. CSS/JS might not load.")
    # Optionally create the directory if it doesn't exist
    # import os
    # if not os.path.exists("static"):
    #     os.makedirs("static")
    #     logger.info("Created static directory.")
    #     app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Import and Include Routers ---
# Import routers AFTER templates/logger might be needed by them
# Note: This structure assumes search.py and workspace.py can import 'templates' from this 'api.py'
# This creates a potential circular dependency if not handled carefully.
# A cleaner way involves dependency injection or a dedicated config module.
# For now, this structure often works in simple FastAPI apps.
try:
    from search import router as search_router
    from workspace import router as workspace_router
    from auth import router as auth_router # Import the new auth router

    app.include_router(auth_router, tags=["Authentication"]) # Include the auth router
    app.include_router(search_router, tags=["Search"])
    app.include_router(workspace_router, tags=["Workspace"])
    logger.info("Included auth, search, and workspace routers.")

except ImportError as e:
    logger.error(f"Failed to import routers: {e}. Check file paths and dependencies.", exc_info=True)
    # You might want to prevent the app from starting if routers fail to load
    raise RuntimeError(f"Failed to import routers: {e}")


# --- Root Endpoint (Optional - can be removed if search.router handles '/') ---
# @app.get("/")
# async def main_root():
#     # Redirect or provide a basic landing page if needed
#     return {"message": "Welcome to SAFLII Search & Workspace API"}


# --- Run Instruction ---
if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    # Use reload=True for development only
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
