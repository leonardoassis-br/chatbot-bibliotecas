import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

from PyPDF2 import PdfReader
from docx import Document

# -------------------------------------------------
# Carregar variáveis de ambiente
# -------------------------------------------------
load_dotenv()

# -------------------------------------------------
# Inicializar app e OpenAI
# -------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ambiente local / piloto
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------------------------------------
# Configuração da biblioteca (1 token interno)
# -------------------------------------------------
TOKEN_MAP = {
    os.getenv("TOKEN_BIBLIOTECA_EXEMPLO"): "bases/biblioteca_exemplo"
}

# -------------------------------------------------
# Modelo da pergunta
# -------------------------------------------------
class Question(BaseModel):
    question: str

# -------------------------------------------------
# Leitura de documentos (TXT, PDF, DOCX)
# -------------------------------------------------
def load_documents(folder_path: str) -> str:
    texts = []

    for file in os.listdir(folder_path):
        path = os.path.join(folder_path, file)

        try:
            # TXT
            if file.lower().endswith(".txt"):
                with open(path, "r", encoding="utf-8") as f:
                    texts.append(f.read())

            # PDF (texto nativo)
            elif file.lower().endswith(".pdf"):
                reader = PdfReader(path)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        texts.append(text)

            # Word (.docx)
            elif file.lower().endswith(".docx"):
                doc = Document(path)
                for paragraph in doc.paragraphs:
                    if paragraph.text.strip():
                        texts.append(paragraph.text)

        except Exception as e:
            print(f"Erro ao ler {file}: {e}")

    return "\n".join(texts)

# -------------------------------------------------
# Rota principal — servir o chat
# -------------------------------------------------
@app.get("/")
def read_chat():
    return FileResponse("static/chat.html")

# -------------------------------------------------
# Rota de pergunta
# -------------------------------------------------
@app.post("/ask")
def ask(payload: Question):
    # Token fica SOMENTE no servidor
    token = os.getenv("TOKEN_BIBLIOTECA_EXEMPLO")

    if not token or token not in TOKEN_MAP:
        raise HTTPException(status_code=401, detail="Token inválido")

    folder = TOKEN_MAP[token]

    if not os.path.exists(folder):
        return {"answer": "Base de conhecimento não encontrada."}

    documents = load_documents(folder)

    if not documents.strip():
        return {"answer": "Não há documentos disponíveis nesta base."}

    prompt = f"""
Você é um assistente institucional de biblioteca.
Responda exclusivamente com base no conteúdo abaixo.
Se a resposta não estiver presente no texto, diga claramente que a informação não foi encontrada.

DOCUMENTOS:
{documents}

PERGUNTA:
{payload.question}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    return {
        "answer": response.choices[0].message.content.strip()
    }
