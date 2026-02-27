from fastapi import FastAPI
from pydantic import BaseModel
from intent_router import route_query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow Android requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Later restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    text: str

@app.get("/")
def root():
    return {"status": "Karn backend running"}

@app.post("/process")
def process_query(query: QueryRequest):
    result = route_query(query.text)
    return {"response": result}