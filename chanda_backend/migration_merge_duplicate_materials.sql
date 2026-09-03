-- ============================================================================
-- Merge duplicate Material Master entries (live database)
-- ============================================================================
-- Problem: the same physical item ended up as multiple materials.material_code
-- rows (e.g. MC037 / MC038, RM-0039 / RM-0040 for "SOCKER PIN LH 17*82").
-- This script finds every such duplicate-name group automatically, picks ONE
-- code to keep per group, re-points every table that references the removed
-- codes to the kept code, adds the removed codes' current_qty on to the kept
-- code, and then deletes the removed rows.
--
-- HOW TO RUN THIS SAFELY:
--   1. BACK UP THE DATABASE FIRST.  pg_dump chanda_store > backup_before_merge.sql
--   2. Run STEP 1 (below) by itself first and read the output -- it only
--      SELECTs, nothing is changed yet. Confirm the "keep" choice for every
--      group looks right (rename kept material_code in the mapping table if not).
--   3. Only then run STEP 2 inside a transaction (it already is, via BEGIN/COMMIT).
--      If anything looks wrong afterwards, ROLLBACK is still possible until COMMIT runs.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- STEP 1: find duplicate groups and decide which code to KEEP.
-- Rule: keep the code with the highest current_qty (most likely the one
-- that's actually been receiving stock); ties broken by the oldest
-- created_at. Review the output below before proceeding -- you can hand-edit
-- keep_code in this temp table if a different code should survive.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS _dup_map;
CREATE TEMP TABLE _dup_map AS
WITH ranked AS (
    SELECT
        material_code,
        material_name,
        current_qty,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY LOWER(TRIM(material_name))
            ORDER BY current_qty DESC NULLS LAST, created_at ASC
        ) AS rn
    FROM materials
)
SELECT
    d.material_code   AS old_code,
    k.material_code   AS keep_code,
    d.material_name,
    d.current_qty      AS old_qty,
    k.current_qty      AS keep_qty
FROM ranked d
JOIN ranked k
    ON LOWER(TRIM(d.material_name)) = LOWER(TRIM(k.material_name))
   AND k.rn = 1
WHERE d.rn > 1;

-- Review before continuing:
SELECT * FROM _dup_map ORDER BY material_name;

-- ---------------------------------------------------------------------------
-- STEP 2: re-point every table that references materials.material_code
-- from old_code to keep_code, oldest-first so history stays intact.
-- ---------------------------------------------------------------------------
UPDATE stock_ledger sl SET material_code = m.keep_code
    FROM _dup_map m WHERE sl.material_code = m.old_code;

UPDATE stock_batches sb SET material_code = m.keep_code
    FROM _dup_map m WHERE sb.material_code = m.old_code;

UPDATE purchases p SET material_code = m.keep_code
    FROM _dup_map m WHERE p.material_code = m.old_code;

UPDATE employee_requests er SET material_code = m.keep_code
    FROM _dup_map m WHERE er.material_code = m.old_code;

UPDATE issues i SET material_code = m.keep_code
    FROM _dup_map m WHERE i.material_code = m.old_code;

UPDATE returns r SET material_code = m.keep_code
    FROM _dup_map m WHERE r.material_code = m.old_code;

UPDATE alerts a SET material_code = m.keep_code
    FROM _dup_map m WHERE a.material_code = m.old_code;

UPDATE critical_spares cs SET material_code = m.keep_code
    FROM _dup_map m WHERE cs.material_code = m.old_code;

UPDATE stock_reconciliations sr SET material_code = m.keep_code
    FROM _dup_map m WHERE sr.material_code = m.old_code;

-- ---------------------------------------------------------------------------
-- STEP 3: fold the removed codes' stock into the kept code, then delete
-- the now-orphaned duplicate material rows.
-- ---------------------------------------------------------------------------
UPDATE materials k
SET current_qty = k.current_qty + sub.total_old_qty,
    opening_qty = k.opening_qty + sub.total_old_opening
FROM (
    SELECT m.keep_code,
           SUM(d.current_qty)  AS total_old_qty,
           SUM(d.opening_qty)  AS total_old_opening
    FROM _dup_map m
    JOIN materials d ON d.material_code = m.old_code
    GROUP BY m.keep_code
) sub
WHERE k.material_code = sub.keep_code;

DELETE FROM materials WHERE material_code IN (SELECT old_code FROM _dup_map);

-- ---------------------------------------------------------------------------
-- STEP 4: sanity check -- should return ZERO rows if the merge worked.
-- ---------------------------------------------------------------------------
SELECT LOWER(TRIM(material_name)) AS name, COUNT(*) AS how_many, ARRAY_AGG(material_code) AS codes
FROM materials
GROUP BY LOWER(TRIM(material_name))
HAVING COUNT(*) > 1;

-- If the STEP 4 result is empty and the earlier _dup_map review looked right:
COMMIT;
-- If something looked wrong instead, run ROLLBACK; here instead of COMMIT.
