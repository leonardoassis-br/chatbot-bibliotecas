import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from PyPDF2 import PdfReader
from docx import Document
import openpyxl

# -------------------------------------------------
# Configuração inicial
# -------------------------------------------------
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TOKEN_MAP = {
    os.getenv("TOKEN_BIBLIOTECA_EXEMPLO"): "bases/biblioteca_exemplo"
}

# -------------------------------------------------
# Modelos
# -------------------------------------------------
class Message(BaseModel):
    role: str
    content: str

class Question(BaseModel):
    question: str
    history: list[Message] = []

# -------------------------------------------------
# Utilidades
# -------------------------------------------------
def extract_keywords(question: str):
    stopwords = {
        "o","a","os","as","de","do","da","dos","das",
        "para","por","em","no","na","nos","nas",
        "qual","quais","é","são","um","uma","meu","minha",
        "seu","sua","como","sobre","isso","isto"
    }

    return [
        w for w in question.lower().split()
        if w not in stopwords and len(w) > 3
    ]

def load_documents(folder_path: str, question: str) -> str:
    texts = []
    keywords = extract_keywords(question)

    for file in os.listdir(folder_path):
        path = os.path.join(folder_path, file)

        try:
            if file.lower().endswith(".txt"):
                with open(path, "r", encoding="utf-8") as f:
                    texts.append(f.read())

            elif file.lower().endswith(".pdf"):
                reader = PdfReader(path)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        texts.append(text)

            elif file.lower().endswith(".docx"):
                doc = Document(path)
                for p in doc.paragraphs:
                    if p.text.strip():
                        texts.append(p.text)

            elif file.lower().endswith(".xlsx"):
                wb = openpyxl.load_workbook(path, data_only=True)
                MAX_MATCHES = 200
                matches = 0

                for sheet in wb.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        row_text = " ".join(
                            str(cell) for cell in row if cell is not None
                        ).lower()

                        if not row_text.strip():
                            continue

                        if keywords and any(k in row_text for k in keywords):
                            texts.append(row_text)
                            matches += 1

                        if matches >= MAX_MATCHES:
                            break
        except Exception as e:
            print(f"Erro ao ler {file}: {e}")

    return "\n".join(texts)

# -------------------------------------------------
# Rotas
# -------------------------------------------------
@app.get("/")
def chat():
    return FileResponse("static/chat.html")

@app.post("/ask")
def ask(payload: Question):
    token = os.getenv("TOKEN_BIBLIOTECA_EXEMPLO")

    if token not in TOKEN_MAP:
        raise HTTPException(status_code=401, detail="Token inválido")

    folder = TOKEN_MAP[token]

    documents = load_documents(folder, payload.question)

    if not documents.strip():
        return {
            "answer": "Não encontrei informações nos documentos para responder a essa pergunta."
        }

    messages = [
        {
            "role": "system",
            "content": (
                "Você é um assistente institucional de biblioteca. "
                "Use apenas os documentos fornecidos. "
                "Considere o histórico recente da conversa apenas para manter coerência."
            )
        }
    ]

    # memória curta (já vem limitada do frontend)
    for m in payload.history:
        messages.append({"role": m.role, "content": m.content})

    # contexto documental
    messages.append({
        "role": "system",
        "content": f"DOCUMENTOS:\n{documents}"
    })

    # pergunta atual
    messages.append({
        "role": "user",
        "content": payload.question
    })

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0
    )

    return {
        "answer": response.choices[0].message.content.strip()
    }
