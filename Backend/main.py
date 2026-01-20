from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import base64
from pipeline import analyze_image_bytes
import traceback

app = FastAPI(title="Biocimentation SEM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze(image: UploadFile = File(...)):
    image_bytes = await image.read()


    try:
        result, overlay_bytes = analyze_image_bytes(image_bytes, filename=image.filename)
    except Exception as e:
        print("Erreur dans pipeline :")
        traceback.print_exc()
        return {"error": str(e)}

    overlay_b64 = base64.b64encode(overlay_bytes).decode("utf-8")

    return {
        "metrics": result,
        "overlay_base64": overlay_b64
    }

@app.post("/llm/analyze")
async def llm_analyze():
    return {
        "status": "coming_soon",
        "message": "Analyse LLM en cours de développement"
    }
