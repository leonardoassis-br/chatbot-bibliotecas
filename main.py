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
# MODELOS
# -------------------------------------------------
class Message(BaseModel):
    role: str
    content: str

class Question(BaseModel):
    question: str
    history: list[Message] = []

# -------------------------------------------------
# CACHE DE DOCUMENTOS (MEMÓRIA VOLÁTIL)
# -------------------------------------------------
DOCUMENT_CACHE = None

# -------------------------------------------------
# LEITURA DE DOCUMENTOS
# -------------------------------------------------
def load_documents(folder_path: str) -> str:
    texts = []

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
                MAX_ROWS = 1000
                rows = 0

                for sheet in wb.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        if rows >= MAX_ROWS:
                            break

                        row_text = " ".join(
                            str(cell) for cell in row if cell is not None
                        )

                        if row_text.strip():
                            texts.append(row_text)

                        rows += 1

        except Exception as e:
            print(f"Erro ao ler {file}: {e}")

    return "\n".join(texts)

# -------------------------------------------------
# ROTAS
# -------------------------------------------------
@app.get("/")
def chat():
    return FileResponse("static/chat.html")

@app.post("/ask")
def ask(payload: Question):
    global DOCUMENT_CACHE

    token = os.getenv("TOKEN_BIBLIOTECA_EXEMPLO")
    if token not in TOKEN_MAP:
        raise HTTPException(status_code=401, detail="Token inválido")

    folder = TOKEN_MAP[token]

    # Cache: carrega documentos apenas uma vez
    if DOCUMENT_CACHE is None:
        DOCUMENT_CACHE = load_documents(folder)

    # -------------------------------------------------
    # PROMPT FINAL — INTERAÇÃO NATURAL DE REFERÊNCIA
    # -------------------------------------------------
    messages = [
        {
            "role": "system",
            "content": (
                "Você atua como um bibliotecário de referência virtual.\n\n"
                "REGRAS DE INTERAÇÃO:\n"
                "- Responda exclusivamente ao que o usuário perguntou.\n"
                "- NÃO antecipe informações, serviços ou explicações.\n"
                "- NÃO liste conteúdos, funções ou possibilidades sem solicitação explícita.\n\n"
                "SAUDAÇÕES:\n"
                "- Se o usuário fizer apenas uma saudação curta "
                "(como \"oi\", \"olá\" ou \"bom dia\"), responda apenas com uma saudação "
                "e convide a pessoa a dizer como pode ajudar.\n\n"
                "CONTEÚDO:\n"
                "- Quando houver uma pergunta, utilize apenas as informações presentes "
                "nos documentos da biblioteca e no acervo.\n"
                "- Explique de forma clara, simples e acolhedora.\n"
                "- Não pressuponha o tipo de biblioteca.\n"
                "- Não mencione instituições, universidades ou sistemas específicos.\n"
                "- Não utilize conhecimento externo.\n\n"
                "Se a pergunta não puder ser respondida com base nos documentos, "
                "informe isso de forma clara."
            )
        }
    ]

    # memória curta (coerência da conversa)
    for m in payload.history:
        messages.append({"role": m.role, "content": m.content})

    # documentos (apenas se houver pergunta real)
    messages.append({
        "role": "system",
        "content": f"ACERVO E DOCUMENTOS:\n{DOCUMENT_CACHE}"
    })

    # pergunta atual
    messages.append({
        "role": "user",
        "content": payload.question
    })

    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=messages,
        temperature=0.3
    )

    return {
        "answer": response.choices[0].message.content.strip()
    }