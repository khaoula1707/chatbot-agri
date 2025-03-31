from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import requests
import os
import json
import uuid
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

app = FastAPI()

# إعدادات CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# حفظ المحادثات حسب session_id
conversations = {}

# ملفات الواجهة
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def lire_page():
    return FileResponse("static/index.html")


# 📥 تحميل جميع ملفات JSON
def charger_donnees_demarches():
    demarches = []
    dossier = "data"
    for nom_fichier in os.listdir(dossier):
        if nom_fichier.endswith(".json"):
            chemin = os.path.join(dossier, nom_fichier)
            with open(chemin, "r", encoding="utf-8") as f:
                contenu = json.load(f)
                if isinstance(contenu, list):
                    demarches.extend(contenu)
                elif isinstance(contenu, dict):
                    demarches.append(contenu)
    return demarches
demarches = charger_donnees_demarches()
print("📂 عدد الملفات:", len(demarches))


# 🗺️ إعداد geopy
geolocator = Nominatim(user_agent="farmer_assistant")

def reverse_geocode(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), language="ar")
        return location.address if location else None
    except GeocoderTimedOut:
        return None


# 💬 Route principale
@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message")
    location = data.get("location", {})
    lat = location.get("latitude")
    lon = location.get("longitude")

    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    print("📩 Message reçu:", user_message)
    print("📍 Coordonnées:", lat, lon)

    # تحويل الإحداثيات إلى اسم مكان
    location_name = reverse_geocode(lat, lon) if lat and lon else None

    # البحث في البيانات
    contexte = ""
    source = "🔵 تم توليد هذه الإجابة من نموذج الذكاء الاصطناعي."
    demarches = charger_donnees_demarches()
    for dem in demarches:
        titre = dem.get("titre", "")
        if titre and (titre.strip() in user_message or user_message.strip() in titre):

            contenu = dem.get("contenu", "")
            contexte = f"{titre}\n{contenu}"
            source = "🟢 تم استخراج هذه المعلومات من وثيقة رسمية."
            break

    # هل المستخدم طلب فقط وصف عام؟
    description_generale = any(
        mot in user_message for mot in [
            "فكرة عامة", "بصفة عامة", "شرح بسيط", "بغيت غير نعرف", "بغا نعرف فقط", "شنو هي"
        ]
    )

    if description_generale:
        system_prompt = """
أنت مساعد ذكي يساعد الفلاحين المغاربة في فهم الإجراءات الإدارية.

✅ إذا طلب المستخدم فقط "فكرة عامة" أو "وصف عام"، فاعطه فقط شرحًا عامًا مبسطًا بدون الدخول في التفاصيل (لا شروط، لا وثائق، لا جهات).

✅ كن واضحًا ومباشرًا، واستعمل لغة سهلة وعربية فصحى.
"""
    else:
        system_prompt = """
أنت مساعد ذكي يساعد الفلاحين المغاربة في فهم الإجراءات الإدارية. أجب دائمًا باللغة العربية، بأسلوب مهني وواضح وسهل الفهم.

✅ إذا كانت معلومات المستخدم غير كافية، فلا تعطه جوابًا مباشرًا. اسأله أسئلة متابعة للحصول على التفاصيل الناقصة (مثل الموقع، نوع الأرض، نوع المشروع، الجهة المسؤولة، إلخ).

✅ إذا كانت إحداثيات الموقع متوفرة، استعملها لتقديم إجابة مناسبة حسب المنطقة.

✅ بعد الحصول على كل المعلومات الضرورية، قدّم له جوابًا منظمًا باستخدام فقرات قصيرة وعناوين واضحة وقوائم مرقّمة عند الحاجة.

❌ لا تستخدم رموز Markdown أو HTML. فقط نص بسيط ومنظم باللغة العربية.
"""

    # إعداد الرسائل حسب session
    if session_id not in conversations:
        conversations[session_id] = [{"role": "system", "content": system_prompt}]
    elif conversations[session_id][0]["role"] == "system":
        conversations[session_id][0]["content"] = system_prompt

    if location_name:
        conversations[session_id].append({
            "role": "system",
            "content": f"📍 موقع المستخدم: {location_name}"
        })

    if contexte:
        conversations[session_id].append({"role": "system", "content": f"معلومات من الملفات:\n{contexte}"})

    conversations[session_id].append({"role": "user", "content": user_message})

    # 🚀 Appel DeepSeek
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": "Bearer sk-66b39bce691041789d358b49a0d878d1",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-chat",
            "messages": conversations[session_id],
            "temperature": 0.7
        }
    )

    result = response.json()

    if "choices" not in result:
        return {"response": "عذرًا، حدث خطأ أثناء الاتصال بخدمة الذكاء الاصطناعي."}

    bot_reply = result["choices"][0]["message"]["content"]
    conversations[session_id].append({"role": "assistant", "content": bot_reply})

    response_data = {"response": f"{source}\n\n{bot_reply}"}
    response = Response(content=json.dumps(response_data), media_type="application/json")
    response.set_cookie(key="session_id", value=session_id)
    return response


# 🔄 Reset session
@app.post("/reset")
async def reset_conversation(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in conversations:
        del conversations[session_id]
    return {"message": "تم بدء محادثة جديدة."}
