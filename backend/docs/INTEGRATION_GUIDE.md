# SIE Public Integration Guide

This guide describes the supported public integration approach for the SIE API. The running deployment's OpenAPI document at `/openapi.json` and interactive documentation at `/docs` are authoritative for the exact endpoints, request fields, scopes, and response schemas available in that deployment.

## Integration principles

- Integrate through the versioned REST API; do not depend on internal Python modules, database tables, or implementation details.
- Use an organization-scoped machine credential issued by an authorized SIE administrator.
- Request only the scopes required for the integration.
- Keep credentials in a managed secret store or protected environment variables. Never commit live credentials or place them in logs, screenshots, issue reports, or source code.
- Use synthetic or explicitly authorized data in development and testing.
- Treat organization identifiers supplied by a client as input, not proof of authorization. The API must enforce tenant scope for every operation.
- Respect documented rate limits, error responses, pagination, and idempotency behavior exposed by the live API contract.

## Typical integration workflow

1. Obtain the base URL for the intended SIE environment from its administrator.
2. Obtain an organization-scoped credential through the approved provisioning process.
3. Read the deployment's OpenAPI schema and select the supported endpoints and required scopes.
4. Build and test requests against a non-production environment using synthetic data.
5. Validate authentication failures, insufficient-scope responses, tenant isolation, malformed input, retries, and duplicate submissions.
6. Confirm auditability and data-retention expectations with the service owner before production use.
7. Store secrets outside source control, restrict access, and define a rotation and revocation procedure.

## Authentication and authorization

Use only the authentication mechanism documented by the target deployment's live OpenAPI schema and administrator. Do not infer credential formats from examples or internal source files. Human administrative authentication and machine-to-machine authentication may have different requirements; integrations should use the machine-client mechanism approved for the environment.

A successful authentication does not grant unrestricted access. Every request must be authorized for the credential's organization and the specific operation being performed. Treat denied requests as a security boundary, not as a signal to retry with broader identifiers or permissions.

## Error handling and operational controls

- Handle authentication and authorization failures explicitly; do not repeatedly retry invalid credentials.
- Use bounded retries with backoff for transient network or service errors.
- Avoid logging authorization headers, secrets, raw personal data, or full sensitive payloads.
- Use stable source-side identifiers where the API contract supports idempotent ingestion.
- Monitor integration failures and coordinate credential rotation with the service administrator.
- Confirm the current environment's retention, deletion, and incident-reporting procedures before onboarding real data.

## Security and intellectual-property boundary

This guide intentionally documents the supported external integration process only. It does not publish internal scoring methods, calibration mappings, proprietary analytics algorithms, database implementation details, customer evaluation reports, or private model architecture. Those details are not part of the public API contract.

For the exact API surface, use `/openapi.json` or `/docs` on the target deployment. If this guide and the live contract differ, follow the live contract and report the documentation discrepancy to the service owner.
