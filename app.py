from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import status
import requests
import os
import json
import uuid
import difflib


app = FastAPI() #  Crées l'application FastAPI principale.

# Middleware CORS .
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Autorise tous les domaines à accéder à l'API .
    allow_methods=["*"], # Autorise toutes les méthodes (GET, POST, etc.).
    allow_headers=["*"], # Accepte tous les types d'en-têtes HTTP .
    allow_credentials=True # Autorise l’envoi de cookies, ce qui est important ici car tu utilises un session_id .
)
# Mémoriser les conversations de chaque utilisateur séparément .
conversations = {}
# Montée du dossier
app.mount("/static", StaticFiles(directory="static"), name="static")
# Afficher le chatbot
@app.get("/")
def lire_page():
    return FileResponse("static/index.html")


# Fonction chargement des donnees 
def charger_donnees_demarches():
    demarches = [] # Initialise une liste vide pour stocker toutes les démarches
    dossier = "data" # Indique  le dossier
    for nom_fichier in os.listdir(dossier): # Parcourt tous les fichiers du dossier
        if nom_fichier.endswith(".json"): # Ne prend que les fichiers .json
            chemin = os.path.join(dossier, nom_fichier) # Construit le chemin complet du fichier
            with open(chemin, "r", encoding="utf-8") as f: # Ouvre le fichier en lecture
                contenu = json.load(f) # Convertit le contenu JSON en dictionnaire ou liste
                if isinstance(contenu, list):# Si le fichier contient plusieurs démarches, on les ajoute toutes
                    demarches.extend(contenu)
                elif isinstance(contenu, dict): #Sinon, on ajoute l’unique démarche trouvée
                    demarches.append(contenu)
    return demarches


# Route /chat : Le cerveau du bot
@app.post("/chat")
async def chat(request: Request):
    # Récupérer le message de l’utilisateur
    data = await request.json()
    user_message = data.get("message")
   
    # Identifier la session utilisateur
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    
    #  Recherche intelligente dans les démarches
    contexte = ""
    source = "🔵 تم توليد هذه الإجابة من نموذج الذكاء الاصطناعي."
    demarches = charger_donnees_demarches()
    titres = [d.get("titre", "") for d in demarches if d.get("titre")]
    titre_proche = difflib.get_close_matches(user_message, titres, n=1, cutoff=0.5)
     # Recherche approximative
    if titre_proche:
        for dem in demarches:
            if dem.get("titre", "").strip() == titre_proche[0].strip():
                contenu = dem.get("contenu", "")
                contexte = f"{dem['titre']}\n{contenu}"
                source = "🟢 تم استخراج هذه المعلومات من وثيقة رسمية."
                break

    # Déterminer si la question est générale
    description_generale = any(
        mot in user_message for mot in [
            "فكرة عامة", "بصفة عامة", "شرح بسيط", "بغيت غير نعرف", "بغا نعرف فقط", "شنو هي"
        ]
    )
    #Générer le prompt système
    system_prompt = """
أنت مساعد ذكي يساعد الفلاحين المغاربة في فهم الإجراءات الإدارية.

 إذا طلب المستخدم فقط "فكرة عامة" أو "وصف عام"، فاعطه فقط شرحًا عامًا مبسطًا بدون الدخول في التفاصيل (لا شروط، لا وثائق، لا جهات).

 كن واضحًا ومباشرًا، واستعمل لغة سهلة وعربية فصحى.
""" if description_generale else """
أنت مساعد ذكي يساعد الفلاحين المغاربة في فهم الإجراءات الإدارية. أجب دائمًا باللغة العربية، بأسلوب مهني وواضح وسهل الفهم.

 إذا كانت معلومات المستخدم غير كافية، فلا تعطه جوابًا مباشرًا. اسأله أسئلة متابعة للحصول على التفاصيل الناقصة (مثل الموقع، نوع الأرض، نوع المشروع، الجهة المسؤولة، إلخ).

 بعد الحصول على كل المعلومات الضرورية، قدّم له جوابًا منظمًا باستخدام فقرات قصيرة وعناوين واضحة وقوائم مرقّمة عند الحاجة.

 لا تستخدم رموز Markdown أو HTML. فقط نص بسيط ومنظم باللغة العربية.
"""

    # Gestion de la conversation 
    if session_id not in conversations:
        conversations[session_id] = [{"role": "system", "content": system_prompt}]
    else:
        conversations[session_id][0]["content"] = system_prompt


    if contexte:
        conversations[session_id].append({"role": "system", "content": f"معلومات من الملفات:\n{contexte}"})

    conversations[session_id].append({"role": "user", "content": user_message})
    messages_to_send = conversations[session_id][:1] + conversations[session_id][-4:]

    # Appel à l'API DeepSeek
    # Envoi à l’API de DeepSeek
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": "Bearer sk-66b39bce691041789d358b49a0d878d1",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-chat",
            "messages": messages_to_send,

            "temperature": 0.5
        },
      
    )
    # Traitement de la réponse
    result = response.json()

    if "choices" not in result:
        return {"response": "عذرًا، حدث خطأ أثناء الاتصال بخدمة الذكاء الاصطناعي."}

    bot_reply = result["choices"][0]["message"]["content"]
    conversations[session_id].append({"role": "assistant", "content": bot_reply})
   # Retour de la réponse au frontend 
    response_data = {"response": f"{source}\n\n{bot_reply}"}
    res = Response(content=json.dumps(response_data), media_type="application/json")
    res.set_cookie(key="session_id", value=session_id)
    return res

#Réinitialisation de session
@app.post("/reset")
async def reset_conversation(request: Request):
    session_id = request.cookies.get("session_id")

    # Supprimer l’ancienne conversation si elle existe
    if session_id and session_id in conversations:
        del conversations[session_id]

    # Générer un nouveau session_id et le renvoyer sans contenu
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key="session_id",
        value=str(uuid.uuid4()),
        httponly=True,
        samesite="Lax"
    )
    return response
