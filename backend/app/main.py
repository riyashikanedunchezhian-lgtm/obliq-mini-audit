from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import audit, clients, documents, session

app = FastAPI(title="OBLIQ Mini Audit Review", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session.router)
app.include_router(clients.router)
app.include_router(documents.router)
app.include_router(audit.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
