WITH DistinctHtml AS (
    SELECT
        htmlsaflii,
        gen_random_uuid() AS new_doc_id -- Generate a new UUID for each distinct htmlsaflii
    FROM
        public.saflii_cases
    GROUP BY
        htmlsaflii -- Ensures we only process unique htmlsaflii values
)
UPDATE public.saflii_cases sc
SET document_id = dh.new_doc_id
FROM DistinctHtml dh
WHERE
    -- Join the main table with the CTE based on the htmlsaflii value
    -- Use IS NOT DISTINCT FROM to handle potential NULL values in htmlsaflii safely,
    -- treating NULL as a distinct value group if needed.
    -- If htmlsaflii is guaranteed NOT NULL, you can use sc.htmlsaflii = dh.htmlsaflii
    sc.htmlsaflii IS NOT DISTINCT FROM dh.htmlsaflii;