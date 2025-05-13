-- Create a partial index to speed up finding rows where document_id is NULL
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_saflii_cases_document_id_null
ON public.saflii_cases (document_id)
WHERE document_id IS NULL;