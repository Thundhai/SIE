"""Service / repository layer.

Every organization-owned model is read and written through
`TenantScopedRepository` (see base.py), which requires an `organization_id`
on every query. There is no helper anywhere in this layer that can query an
organization-owned table without a tenant filter — that is SIE's
query-level tenant isolation guarantee.
"""
