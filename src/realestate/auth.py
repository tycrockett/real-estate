from __future__ import annotations

import os
from functools import lru_cache

import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt

load_dotenv()

AUTH0_ALGORITHMS = ["RS256"]


def _get_domain():
    return os.environ.get("AUTH0_DOMAIN", "")


def _get_audience():
    return os.environ.get("AUTH0_AUDIENCE", "")


@lru_cache()
def _get_jwks():
    domain = _get_domain()
    if not domain:
        return None
    url = f"https://{domain}/.well-known/jwks.json"
    resp = requests.get(url, timeout=10)
    return resp.json()


def _get_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request) -> dict:
    """FastAPI dependency — validates the JWT and returns the user payload."""
    domain = _get_domain()
    audience = _get_audience()

    if not domain:
        # Auth not configured — allow all requests (dev mode)
        return {"sub": "dev", "email": "dev@local"}

    token = _get_token(request)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        print(f"[AUTH DEBUG] No token. Auth header: '{auth_header[:50]}' Domain: {domain} Audience: {audience}")
        raise HTTPException(status_code=401, detail="Missing authorization token")

    jwks = _get_jwks()
    if not jwks:
        raise HTTPException(status_code=500, detail="Could not fetch JWKS")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token header")

    rsa_key = {}
    for key in jwks.get("keys", []):
        if key["kid"] == unverified_header.get("kid"):
            rsa_key = key
            break

    if not rsa_key:
        raise HTTPException(status_code=401, detail="Unable to find signing key")

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=AUTH0_ALGORITHMS,
            audience=audience,
            issuer=f"https://{domain}/",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        # Debug: decode without verification to see what's in the token
        try:
            unverified = jwt.get_unverified_claims(token)
            print(f"[AUTH DEBUG] Token iss: {unverified.get('iss')}, aud: {unverified.get('aud')}")
            print(f"[AUTH DEBUG] Expected iss: https://{domain}/, aud: {audience}")
        except:
            pass
        raise HTTPException(status_code=401, detail=f"Token validation failed: {e}")
