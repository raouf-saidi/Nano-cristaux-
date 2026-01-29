from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os, base64, traceback, json
from pipeline import analyze_image_bytes
from openai import OpenAI

app = FastAPI(title="Biocimentation SEM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# PIPELINE (quantif + overlay)
# =========================
@app.post("/analyze")
async def analyze(image: UploadFile = File(...)):
    image_bytes = await image.read()

    try:
        result, overlay_bytes = analyze_image_bytes(image_bytes, filename=image.filename)
    except Exception as e:
        print("Erreur dans pipeline :")
        traceback.print_exc()
        return {"error": str(e)}

    overlay_b64 = base64.b64encode(overlay_bytes).decode("utf-8") if overlay_bytes else ""

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

# =========================
# LLM CHAT (robuste image)
# =========================
client = OpenAI(api_key="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")

ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}

CHAT_SYSTEM = """Tu es un assistant scientifique spécialisé en images SEM/MEB
liées à la biocimentation (CaCO3).

Règles :
- Réponds en français
- Sois prudent et factuel
- N'invente pas de mesures
- Si l’image est floue ou peu exploitable, dis-le clairement
- Donne des interprétations qualitatives (pontage faible / moyen / fort)
- Propose des recommandations expérimentales si pertinent
"""

@app.post("/llm_chat")
async def llm_chat(
    message: str = Form(...),
    history_json: str = Form("[]"),
    image: UploadFile | None = File(None),
):
    # parse historique (optionnel, pour plus tard)
    try:
        history = json.loads(history_json) if history_json else []
    except Exception:
        history = []

    user_content = [{"type": "input_text", "text": message}]

    # image optionnelle + validation
    if image is not None:
        if image.content_type not in ALLOWED_MIME:
            raise HTTPException(
                status_code=400,
                detail=f"Format image non supporté: {image.content_type}. Formats acceptés: {sorted(ALLOWED_MIME)}"
            )

        img_bytes = await image.read()
        if not img_bytes or len(img_bytes) < 50:
            raise HTTPException(status_code=400, detail="Image vide ou invalide")

        # mime propre pour data-url
        if image.content_type == "image/png":
            mime = "image/png"
        elif image.content_type in ("image/jpeg", "image/jpg"):
            mime = "image/jpeg"
        elif image.content_type == "image/webp":
            mime = "image/webp"
        elif image.content_type == "image/gif":
            mime = "image/gif"
        else:
            mime = "image/png"  # fallback

        b64 = base64.b64encode(img_bytes).decode("utf-8")
        user_content.append({
            "type": "input_image",
            "image_url": f"data:{mime};base64,{b64}"
        })

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": CHAT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )

    return {"reply": resp.output_text}
