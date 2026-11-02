"""Generate an Ed25519 key pair for SIE-2 tenant assertions.

Run it on your own machine, never in CI or a shared shell:

    python -m scripts.generate_tenant_assertion_key --kid sie-2026-10

It prints two values and stores nothing:

- COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY (SECRET): the private JWK,
  for Public SIE's hosting dashboard only.
- The public key map, for CC_SERVICE_TENANT_ASSERTION_PUBLIC_KEYS and
  DOMAIN_SERVICE_TENANT_ASSERTION_PUBLIC_KEYS on Commercial Core. It holds
  no private component and is safe to share.

To rotate, add the new kid to the public map next to the old one, switch
the signing key and KEY_ID, then remove the old kid after at least 60
seconds plus a deploy (owner decision D1).
"""

from __future__ import annotations

import argparse
import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate(kid: str) -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    x = _b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    d = _b64(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()))
    private_jwk = json.dumps({"kty": "OKP", "crv": "Ed25519", "x": x, "d": d}, separators=(",", ":"))
    public_map = json.dumps({kid: {"kty": "OKP", "crv": "Ed25519", "x": x}}, separators=(",", ":"))
    return private_jwk, public_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--kid", required=True, help="Key id, 1-64 characters, e.g. sie-2026-10.")
    args = parser.parse_args(argv)
    if not 1 <= len(args.kid) <= 64:
        parser.error("--kid must be 1-64 characters")
    private_jwk, public_map = generate(args.kid)
    print("COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY (SECRET: Public SIE only, never commit or share):")
    print(private_jwk)
    print()
    print(f"COMMERCIAL_CORE_TENANT_ASSERTION_KEY_ID={args.kid}")
    print()
    print("CC_SERVICE_TENANT_ASSERTION_PUBLIC_KEYS and DOMAIN_SERVICE_TENANT_ASSERTION_PUBLIC_KEYS (public):")
    print(public_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
