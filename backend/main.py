import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from livekit import api  # This is the correct import
from dotenv import load_dotenv
from pydantic import BaseModel

# Import our database and models
from . import models, database

# Load environment variables
load_dotenv()

# Initialize Database Tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

# 1. CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas ---
class TokenRequest(BaseModel):
    name: str
    email: str

class TicketCreate(BaseModel):
    customer_name: str
    customer_email: str
    issue_description: str
    status: str = "Open"

# --- Routes ---

@app.post("/api/token")
async def get_token(req: TokenRequest):
    lk_api_key = os.getenv("LIVEKIT_API_KEY")
    lk_api_secret = os.getenv("LIVEKIT_API_SECRET")
    lk_url = os.getenv("LIVEKIT_URL")

    if not lk_api_key or not lk_api_secret:
        raise HTTPException(status_code=500, detail="Server misconfigured: Missing LiveKit keys")

    # --- FIXED: New Token Generation Code (v1.0+) ---
    token = api.AccessToken(lk_api_key, lk_api_secret) \
        .with_identity(req.name) \
        .with_name(req.name) \
        .with_grants(api.VideoGrants(
            room_join=True,
            room="support-room"
        ))

    return {"token": token.to_jwt(), "ws_url": lk_url}


@app.post("/api/tickets")
def create_ticket(ticket: TicketCreate, db: Session = Depends(database.get_db)):
    db_ticket = models.Ticket(
        customer_name=ticket.customer_name,
        customer_email=ticket.customer_email,
        issue_description=ticket.issue_description,
        status=ticket.status
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


@app.get("/api/tickets")
def read_tickets(status: str = None, db: Session = Depends(database.get_db)):
    query = db.query(models.Ticket)
    if status:
        query = query.filter(models.Ticket.status == status)
    return query.all()

# --- Static File Serving ---

# 1. Mount the "frontend" folder
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# 2. Serve index.html at the root URL
@app.get("/")
async def read_root():
    return FileResponse('frontend/index.html')

# 3. Serve other HTML pages
@app.get("/{page_name}.html")
async def read_page(page_name: str):
    return FileResponse(f"frontend/{page_name}.html")