"""Minimal CORS and bearer-token middleware (no extra dependencies)."""
from __future__ import annotations

import hmac

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.middleware.gzip import GZipMiddleware


class CorsMiddleware:
    """Allow the teammate's frontend dev server (configured origins only) to call /api/."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin != "null" and origin in settings.CORS_ALLOWED_ORIGINS
        if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            same_origin = origin == f"{request.scheme}://{request.get_host()}"
            untrusted_origin = origin is not None and not (same_origin or allowed)
            untrusted_site = origin is None and request.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site")
            if untrusted_origin or untrusted_site:
                return JsonResponse({"error": "untrusted request origin"}, status=403)
        if request.method == "OPTIONS" and allowed:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Range"
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response["Access-Control-Expose-Headers"] = "Content-Range, Accept-Ranges, Content-Length, ETag"
        return response


class TokenAuthMiddleware:
    """If EGOHAND_API_TOKEN is set, every /api/ request needs 'Authorization: Bearer <token>'."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = settings.API_TOKEN
        if token and request.path.startswith("/api/") and request.method != "OPTIONS" \
                and request.path != "/api/health":
            header = request.headers.get("Authorization", "")
            supplied = header[7:] if header.startswith("Bearer ") else request.GET.get("token", "")
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JsonResponse({"error": "unauthorized"}, status=401)
        return self.get_response(request)


class TextGZipMiddleware(GZipMiddleware):
    """Gzip JSON/text only. Media and binary files (MP4 byte ranges, JPEG, NPZ) are already
    compressed, and gzip-encoding a 206 partial response would break HTTP Range semantics."""
    COMPRESSIBLE = ("application/json", "text/", "application/javascript")

    def process_response(self, request, response):
        content_type = response.get("Content-Type", "")
        if response.status_code == 206 or not content_type.startswith(self.COMPRESSIBLE):
            return response
        return super().process_response(request, response)
