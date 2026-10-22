from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from auth.database import init_pool
from auth.controllers.auth_controller import router as auth_router
from auth.controllers.user_controller import router as user_router

app = FastAPI(title="FnxDirect Auth API", docs_url=None, redoc_url=None)


@app.on_event("startup")
def startup():
    init_pool()


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    # Never leak internal details to the client
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app.include_router(auth_router)
app.include_router(user_router)


@app.get("/health")
def health():
    return {"status": "ok"}
