import hashlib
import re


def normalize_text(text):
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def hash_chunk(text):
    clean_text = normalize_text(text)
    return hashlib.sha256(clean_text.encode("utf-8")).hexdigest()