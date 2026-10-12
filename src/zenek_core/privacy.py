import re

SECRET=re.compile(r"(?:\bsk-[A-Za-z0-9_-]{16,}|\bBearer\s+[A-Za-z0-9._-]{12,}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|(?:hasło|password|api[_ -]?key|secret|token)\s*[:=]\s*\S{6,})",re.I)

def safe_text(value,limit=16000):
    if not isinstance(value,str) or len(value)>limit:raise ValueError("Nieprawidłowy rozmiar tekstu")
    if SECRET.search(value):raise ValueError("Wykryto możliwy sekret. Usuń go przed zapisaniem lub wysłaniem.")
    return value
