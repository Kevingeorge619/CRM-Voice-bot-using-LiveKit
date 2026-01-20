import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from livekit import api 
from dotenv import load_dotenv
from pydantic import BaseModel
from . import models, database

load_dotenv()

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenRequest(BaseModel):
    name: str
    email: str

class TicketCreate(BaseModel):
    customer_name: str
    customer_email: str
    issue_description: str
    status: str = "Open"

class TicketAppend(BaseModel):
    additional_info: str

@app.post("/api/token")
async def get_token(req: TokenRequest):
    lk_api_key = os.getenv("LIVEKIT_API_KEY")
    lk_api_secret = os.getenv("LIVEKIT_API_SECRET")
    lk_url = os.getenv("LIVEKIT_URL")

    if not lk_api_key or not lk_api_secret:
        raise HTTPException(status_code=500, detail="Server misconfigured: Missing LiveKit keys")
  
    token = api.AccessToken(lk_api_key, lk_api_secret) \
        .with_identity(req.name) \
        .with_name(req.name) \
        .with_metadata(req.email) \
        .with_grants(api.VideoGrants(room_join=True, room="support-room"))

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

# UPDATE TICKET STATUS
@app.put("/api/tickets/{ticket_id}/close")
def close_ticket(ticket_id: int, db: Session = Depends(database.get_db)):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket.status = "Closed"
    db.commit()
    return {"message": "Ticket closed successfully"}

# CLEAR ALL TICKETS 
@app.delete("/api/tickets")
def clear_all_tickets(db: Session = Depends(database.get_db)):
    db.query(models.Ticket).delete()
    db.commit()
    return {"message": "All tickets deleted"}

@app.put("/api/tickets/{ticket_id}/append")
def append_ticket_info(ticket_id: int, update: TicketAppend, db: Session = Depends(database.get_db)):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket.issue_description += f"\n\n[Update]: {update.additional_info}"
    db.commit()
    return {"message": "Ticket updated", "id": ticket.id}


current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
frontend_path = os.path.join(root_dir, "frontend")

if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/{page_name}.html")
async def read_page(page_name: str):
    page_file = os.path.join(frontend_path, f"{page_name}.html")
    if os.path.exists(page_file):
        return FileResponse(page_file)
    return {"error": "Page not found"}