from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.db import Base, engine, get_db
from app import models
from app.openai_client import chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="HackAlem AI backend")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
def ask(prompt: str):
    resp = chat(messages=[{"role": "user", "content": prompt}])
    return {"answer": resp.choices[0].message.content}

@app.get("/items")
def list_items(db: Session = Depends(get_db)):
    return db.query(models.Item).all()
