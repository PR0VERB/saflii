import os
import traceback
import uuid # Added for generating UUIDs
import time # Added for retry delay
import httpx # Added for specific network error handling
from supabase import create_client, Client
from dotenv import load_dotenv
from postgrest.exceptions import APIError

# Load environment variables from .env file (if it exists in the root)
# Assumes SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set either in .env or system env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env')) # Look for .env in parent dir

# --- Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
# IMPORTANT: Use the SERVICE KEY for operations like UPDATE that modify data
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") # Changed variable name
# SQL_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'temp_update_script.sql') # No longer needed

# --- Configuration ---
BATCH_SIZE = 20 # Number of distinct htmlsaflii values to fetch per batch
UPDATE_SUB_BATCH_SIZE = 10 # Number of rows to update in a single UPDATE statement (Reduced from 20)
MAX_RETRIES = 3 # Max retries for network errors during sub-batch update
RETRY_DELAY = 1 # Delay in seconds between retries

# --- Batch Update Logic ---
def execute_batch_update(supabase: Client):
    """Fetches distinct htmlsaflii values in batches and updates document_id one by one."""
    batch_num = 0
    total_updated_groups = 0
    while True:
        batch_num += 1
        print(f"\n--- Processing Batch {batch_num} ---")

        # 1. Fetch a batch of distinct htmlsaflii values needing update
        distinct_htmlsaflii_to_process = []
        try:
            print(f"Fetching up to {BATCH_SIZE} distinct htmlsaflii values with NULL document_id...")
            # Use select distinct on the column directly
            # Note: Supabase Python client might not directly support DISTINCT in this way.
            # Falling back to RPC or a view might be needed if this fails.
            # Let's try a workaround using group() which implies distinct.
            # We only need the htmlsaflii value.
            response = supabase.table('saflii_cases')\
                .select('htmlsaflii')\
                .is_('document_id', 'null')\
                .limit(BATCH_SIZE)\
                .execute()

            if response.data:
                 # Extract unique htmlsaflii values from the fetched rows
                 seen_htmlsaflii = set()
                 for row in response.data:
                     if row['htmlsaflii'] not in seen_htmlsaflii:
                         distinct_htmlsaflii_to_process.append(row['htmlsaflii'])
                         seen_htmlsaflii.add(row['htmlsaflii'])
                 print(f"Fetched {len(distinct_htmlsaflii_to_process)} distinct htmlsaflii values for this batch.")
            else:
                 print("No more rows with NULL document_id found. Update complete.")
                 break # Exit the loop if no more rows need updating

        except Exception as e:
            print(f"Error fetching distinct htmlsaflii values for batch {batch_num}: {e}")
            traceback.print_exc()
            print("Stopping batch processing due to error during fetch.")
            break

        # 2. Iterate through the fetched distinct htmlsaflii values and update one by one
        updated_in_batch = 0
        for htmlsaflii_value in distinct_htmlsaflii_to_process:
            if htmlsaflii_value is None: # Skip if somehow a NULL value was fetched
                print("Skipping NULL htmlsaflii value.")
                continue

            try:
                # Count rows for this specific htmlsaflii value first
                count_response = supabase.table('saflii_cases')\
                    .select('htmlsaflii', count='exact')\
                    .eq('htmlsaflii', htmlsaflii_value)\
                    .is_('document_id', 'null')\
                    .execute()

                row_count = count_response.count if hasattr(count_response, 'count') else 'Unknown'
                print(f"  Found {row_count} rows for htmlsaflii: {str(htmlsaflii_value)[:50]}...")

                if row_count == 0:
                    print("  Skipping update as count is 0 (already processed or no match).")
                    continue # Skip to the next htmlsaflii value

                if row_count == 'Unknown':
                     print("  Warning: Could not determine row count before update.")
                     # Decide if you want to proceed anyway or stop. Let's proceed cautiously.

                # Proceed with update, but fetch IDs and update in sub-batches
                new_doc_id = str(uuid.uuid4())
                print(f"  Processing update for {row_count} rows (New ID: {new_doc_id}). Fetching IDs...")

                # Fetch primary keys (assuming 'id') of rows to update for this htmlsaflii
                ids_to_update = []
                fetch_ids_response = supabase.table('saflii_cases')\
                    .select('id')\
                    .eq('htmlsaflii', htmlsaflii_value)\
                    .is_('document_id', 'null')\
                    .execute()

                if fetch_ids_response.data:
                    ids_to_update = [row['id'] for row in fetch_ids_response.data]
                    print(f"    Fetched {len(ids_to_update)} IDs.")
                else:
                    print(f"    Warning: Found 0 IDs to update for {htmlsaflii_value}, although count was {row_count}. Skipping update.")
                    continue # Skip to next htmlsaflii

                # Update in sub-batches
                total_updated_for_this_group = 0
                update_error_occurred = False
                for i in range(0, len(ids_to_update), UPDATE_SUB_BATCH_SIZE):
                    sub_batch_ids = ids_to_update[i:i + UPDATE_SUB_BATCH_SIZE]
                    print(f"    Updating sub-batch {i // UPDATE_SUB_BATCH_SIZE + 1} ({len(sub_batch_ids)} rows)...")
                    retries = 0
                    while retries < MAX_RETRIES:
                        try:
                            update_response = supabase.table('saflii_cases')\
                                .update({'document_id': new_doc_id})\
                                .in_('id', sub_batch_ids)\
                                .execute()

                            # Simple check: if no exception, assume success for this sub-batch
                            if update_response: # Check if response object exists, basic success indicator
                                total_updated_for_this_group += len(sub_batch_ids) # Assume all in sub-batch were updated if no error
                            else:
                                # This case might indicate an issue even without an exception
                                print(f"    Warning: Update sub-batch {i // UPDATE_SUB_BATCH_SIZE + 1} returned an unexpected response: {update_response}")
                            break # Success, exit retry loop

                        except httpx.RemoteProtocolError as network_error:
                            retries += 1
                            print(f"    Network Error (RemoteProtocolError) updating sub-batch {i // UPDATE_SUB_BATCH_SIZE + 1}: {network_error}. Retry {retries}/{MAX_RETRIES}...")
                            if retries >= MAX_RETRIES:
                                print(f"    ERROR: Max retries exceeded for sub-batch {i // UPDATE_SUB_BATCH_SIZE + 1}.")
                                traceback.print_exc() # Print traceback for the final failure
                                update_error_occurred = True
                                break # Exit retry loop, error flag is set
                            time.sleep(RETRY_DELAY) # Wait before retrying
                            # Continue to next retry iteration

                        except Exception as sub_batch_error:
                            print(f"    ERROR updating sub-batch {i // UPDATE_SUB_BATCH_SIZE + 1} for htmlsaflii: {htmlsaflii_value}: {sub_batch_error}")
                            # Check if it's a timeout error
                            if isinstance(sub_batch_error, APIError) and sub_batch_error.code == '57014':
                                print(f"      Timeout occurred even with sub-batch size {UPDATE_SUB_BATCH_SIZE}. Consider reducing size further or check DB performance.")
                            else:
                                traceback.print_exc()
                            update_error_occurred = True
                            break # Stop processing sub-batches for this htmlsaflii on non-network error, exit retry loop

                    if update_error_occurred: # If an error occurred in the retry loop, break the outer sub-batch loop
                        break

                if update_error_occurred:
                    print(f"  Stopping processing for this batch due to update error in sub-batch for {htmlsaflii_value}.")
                    break # Stop processing the entire batch

                if total_updated_for_this_group > 0:
                    print(f"    Successfully updated {total_updated_for_this_group} rows for {htmlsaflii_value}.")
                    updated_in_batch += 1 # Count this group as successfully processed
                elif not update_error_occurred:
                     print(f"    No rows seem to have been updated for {htmlsaflii_value} (might have been updated concurrently).")


            except Exception as e:
                 # Catch potential exceptions during ID fetching or outer logic
                 print(f"  ERROR: An unexpected Python exception occurred processing htmlsaflii: {htmlsaflii_value}: {e}")
                 traceback.print_exc()
                 print("  Stopping processing for this batch due to error.")
                 break # Stop processing this batch

        total_updated_groups += updated_in_batch
        print(f"--- Batch {batch_num} finished. Updated {updated_in_batch} distinct htmlsaflii groups. Total updated: {total_updated_groups} ---")

        # If an error occurred during the inner loop, the outer loop will also break here
        if updated_in_batch < len(distinct_htmlsaflii_to_process) and len(distinct_htmlsaflii_to_process) > 0 :
             print("Batch processing stopped early due to an error during updates.")
             break


    print(f"\nBatch processing finished. Total distinct htmlsaflii groups updated: {total_updated_groups}")


# --- Main Execution Function ---
def main():
    """Initializes client and starts the batch update process."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables must be set.")
        print("Ensure they are in your system environment or a .env file in the project root.")
        return

    supabase_client: Client | None = None # Renamed variable for clarity
    try:
        print("Initializing Supabase client...")
        supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("Supabase client initialized successfully.")

        # Start the batch update process
        execute_batch_update(supabase_client)

    except Exception as e:
        print(f"An error occurred during initialization or execution: {e}")
        traceback.print_exc()
    finally:
        # Clean up if needed (e.g., close connections if using a different DB library)
        pass

if __name__ == "__main__":
    main() # Call the main function