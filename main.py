from typing import Union
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from app.routes import products_route, sales_route, dashboard_route

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api")
async def read_root():
    # db_url = os.getenv("PROJECT_NAME")
    db_url = settings.PROJECT_NAME
    print(db_url)
    
    return {"state": "api OK"}

app.include_router(products_route.router, prefix='/api')
app.include_router(sales_route.router, prefix='/api')
app.include_router(dashboard_route.router, prefix='/api')

if __name__ == "__main__":
    uvicorn.run("main:app", host='0.0.0.0', port=8000, reload=True)