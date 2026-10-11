# Public Architecture Boundary

SIE's public repository contains the components and interfaces required to integrate with the public SIE service. Internal commercial implementation details, customer-specific operational data, and non-public evaluation artifacts are maintained separately and are not part of the public documentation contract.

## Public integration guidance

- Use the documented public API and integration contracts for supported interactions.
- Treat API responses and published schemas as the source of truth for externally observable behavior.
- Configure deployments through environment variables and a managed secret store; do not commit credentials or production configuration values.
- Use synthetic or explicitly authorized data in public examples, fixtures, and evaluation reports.
- Keep internal model implementation, proprietary risk/intelligence methods, customer-specific calibration outcomes, and internal database ownership details in access-controlled documentation.

This document intentionally describes the public boundary at a high level. It does not document private implementation details or customer-specific evaluation results.
