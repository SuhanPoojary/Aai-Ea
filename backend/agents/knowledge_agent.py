"""Knowledge Retrieval Agent: asks the RAG retriever for relevant policy chunks."""
from rag.retrieval import run as retrieve_policy_chunks

def run(query: str, intent=None):
    return retrieve_policy_chunks(query, intent=intent)
