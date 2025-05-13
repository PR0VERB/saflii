-- Function to update document_id for a specific htmlsaflii with increased timeout
CREATE OR REPLACE FUNCTION update_document_id_for_htmlsaflii(
    target_htmlsaflii TEXT,
    new_document_id UUID
)
RETURNS INTEGER -- Returns the number of rows updated
LANGUAGE plpgsql
AS $$
DECLARE
  updated_count INTEGER;
BEGIN
  -- Set timeout for this transaction only (900000ms = 15 minutes)
  SET LOCAL statement_timeout = 900000;

  -- Perform the update
  UPDATE public.saflii_cases
  SET document_id = new_document_id
  WHERE htmlsaflii IS NOT DISTINCT FROM target_htmlsaflii -- Use IS NOT DISTINCT FROM for NULL safety if htmlsaflii can be NULL
    AND document_id IS NULL;

  -- Get the number of rows updated
  GET DIAGNOSTICS updated_count = ROW_COUNT;

  -- Reset timeout to default for the rest of the session (optional, good practice)
  RESET statement_timeout;

  RETURN updated_count;

EXCEPTION
  WHEN OTHERS THEN
    -- Reset timeout even if an error occurs
    RESET statement_timeout;
    -- Re-raise the error
    RAISE;
END;
$$;