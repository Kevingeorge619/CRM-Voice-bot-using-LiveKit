from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from .database import Base

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, index=True)
    customer_email = Column(String)
    issue_description = Column(Text)
    status = Column(String, default="Open")  # Open, Closed
    created_at = Column(DateTime, default=datetime.utcnow)