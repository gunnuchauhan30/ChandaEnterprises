-- Fixes a race condition where two near-simultaneous requests (e.g. a
-- double-click on "Try Fulfill" in Backorders, or the browser retrying a
-- failed request) could both compute the same next issue_no / grn_no /
-- request_no / return_no / batch_no from a COUNT(*) query and then collide
-- on the UNIQUE constraint, causing a 500 error.
--
-- Run this ONCE against your existing production database. It is safe to
-- run even with existing data -- each sequence is seeded to continue right
-- after the highest number already in use, so no numbers are reused or skipped.

CREATE SEQUENCE IF NOT EXISTS purchases_grn_no_seq;
CREATE SEQUENCE IF NOT EXISTS employee_requests_request_no_seq;
CREATE SEQUENCE IF NOT EXISTS issues_issue_no_seq;
CREATE SEQUENCE IF NOT EXISTS returns_return_no_seq;
CREATE SEQUENCE IF NOT EXISTS purchases_batch_no_seq;

SELECT setval(
    'purchases_grn_no_seq',
    COALESCE((SELECT MAX(NULLIF(regexp_replace(grn_no, '\D', '', 'g'), '')::bigint) FROM purchases), 0) + 1,
    false
);

SELECT setval(
    'employee_requests_request_no_seq',
    COALESCE((SELECT MAX(NULLIF(regexp_replace(request_no, '\D', '', 'g'), '')::bigint) FROM employee_requests), 0) + 1,
    false
);

SELECT setval(
    'issues_issue_no_seq',
    COALESCE((SELECT MAX(NULLIF(regexp_replace(issue_no, '\D', '', 'g'), '')::bigint) FROM issues), 0) + 1,
    false
);

SELECT setval(
    'returns_return_no_seq',
    COALESCE((SELECT MAX(NULLIF(regexp_replace(return_no, '\D', '', 'g'), '')::bigint) FROM returns), 0) + 1,
    false
);

SELECT setval(
    'purchases_batch_no_seq',
    COALESCE((SELECT MAX(NULLIF(regexp_replace(batch_no, '\D', '', 'g'), '')::bigint) FROM purchases WHERE batch_no LIKE 'LOT-%'), 0) + 1,
    false
);
