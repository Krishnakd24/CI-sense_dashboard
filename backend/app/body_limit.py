"""Bound multipart bodies before Starlette buffers uploads."""
from starlette.responses import JSONResponse
class BodyLimit:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST","PUT","PATCH"):
            return await self.app(scope, receive, send)
        maximum = 6 * 1024 * 1024 if scope["path"] in ("/analyses", "/admin/analyses") else 64 * 1024
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect": return
            chunk = message.get("body", b""); size += len(chunk)
            if size > maximum:
                return await JSONResponse({"detail":"Request body is too large."},status_code=413)(scope,receive,send)
            chunks.append(chunk)
            if not message.get("more_body",False): break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type":"http.request","body":b"".join(chunks),"more_body":False}
            return await receive()
        return await self.app(scope,replay,send)
