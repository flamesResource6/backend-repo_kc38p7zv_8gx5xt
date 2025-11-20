import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EnergyInput(BaseModel):
    tilt: float = Field(25, ge=0, le=90, description="Panel tilt in degrees")
    azimuth: float = Field(180, ge=0, le=360, description="0=N,90=E,180=S,270=W")
    irradiance: float = Field(4.8, ge=0, description="kWh/m^2/day baseline")
    area: float = Field(18, ge=0, description="Array area in m^2")


class EnergyOutput(BaseModel):
    daily: float
    monthly: float
    score: int


def compute_energy(inp: EnergyInput) -> EnergyOutput:
    # Mirror the lightweight pseudo-model used in the frontend
    tiltFactor = 1 - abs(inp.tilt - 30) / 120  # peak near 30deg
    facingSouthFactor = 1 - min(abs(inp.azimuth - 180), 180) / 240  # peak at south
    k = max(0.5, tiltFactor * 0.9 + facingSouthFactor * 0.6)
    dailyKWh = inp.irradiance * inp.area * 0.18 * k  # ~18% efficiency
    monthlyKWh = dailyKWh * 30
    score = round(min(100, (k / 1.5) * 100))
    return EnergyOutput(daily=max(0, dailyKWh), monthly=max(0, monthlyKWh), score=score)


class SubscribeInput(BaseModel):
    email: EmailStr


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.post("/api/energy/estimate", response_model=EnergyOutput)
def energy_estimate(payload: EnergyInput):
    return compute_energy(payload)


@app.post("/api/subscribe")
def subscribe(payload: SubscribeInput):
    # Try to persist to database if configured, otherwise accept anyway
    try:
        from database import create_document
        doc_id = create_document("subscriber", {"email": payload.email})
        return {"status": "ok", "stored": True, "id": doc_id}
    except Exception:
        # Graceful fallback if DB isn't configured
        return {"status": "ok", "stored": False}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
