"""
Opt-in workaround for networks that intercept HTTPS (corporate proxies, some Windows dev machines):
set DISABLE_SSL_VERIFY=1 in .env to skip certificate checks for outgoing requests.
Never enable it in production.
"""
import os
import ssl

_applied = False


def apply_if_enabled():
    global _applied
    if _applied or os.getenv("DISABLE_SSL_VERIFY", "").strip().lower() not in {"1", "true", "yes"}:
        return
    _applied = True

    ssl._create_default_https_context = ssl._create_unverified_context
    os.environ["CURL_CA_BUNDLE"] = ""
    os.environ["REQUESTS_CA_BUNDLE"] = ""

    import httpx

    def _without_verify(original_init):
        def patched_init(self, *args, **kwargs):
            kwargs["verify"] = False
            original_init(self, *args, **kwargs)
        return patched_init

    httpx.Client.__init__ = _without_verify(httpx.Client.__init__)
    httpx.AsyncClient.__init__ = _without_verify(httpx.AsyncClient.__init__)
