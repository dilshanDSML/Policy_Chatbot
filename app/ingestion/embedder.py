from functools import lru_cache

from fastembed import TextEmbedding


@lru_cache
def get_embedder():
    return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


def embed_documents(texts):
    return [vector.tolist() for vector in get_embedder().embed(texts)]


def embed_query(text):
    return next(get_embedder().query_embed(text)).tolist()
