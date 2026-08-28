"""Authentication: establishing which org a request belongs to (NFR-001, #20).

`app/db/scoping.py` filters every query by org_id, and that part was always
correct. What was missing is a trustworthy identity feeding it — the org came
from an unverified `X-Org-Id` header any caller could set to any value.
"""
