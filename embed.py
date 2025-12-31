import uuid, logging
import chromadb
import os

def get_code_embedding(code: str, provider: str):
    """
    Generate an embedding for `code` using a specified provider.
    `provider` should be one of: "openai", "google", "anthropic"
    """
    provider = provider.lower()

    try:
        if provider == "openai":
            import openai
            api_key = os.getenv("OPENAI_API_KEY")
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                input=code,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding

        elif provider == "google-genai":
            from google.genai import Client
            from google.genai.types import HttpOptions, EmbedContentConfig
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION")
            if not project:
                raise ValueError("GOOGLE_API_KEY missing in .env")
            client = Client(vertexai=True, project=project, location=location, http_options=HttpOptions(api_version="v1"))
            embedding_resp = client.models.embed_content(
                model = "gemini-embedding-001",
                contents = code,
                config = EmbedContentConfig(output_dimensionality=1536)
            )
            return embedding_resp.embeddings[0]

        elif provider == "anthropic":
            logging.error("Anthropic does not provide embeddings natively. Please choose a different provider.")
            return None
        else:
            logging.error(f"Unknown provider: {provider}")
            return None

    except Exception as e:
        logging.error(f"Error generating embedding for provider {provider}: {e}")
        return None


def generate_code_embeddings(code_chunks, provider):
    embeddings = []
    for chunk in code_chunks:
        text = f"Instruction: {chunk['instruction']}\nCode:\n{chunk['code']}\nSummary:\n{chunk['summary']}"
        embedding = get_code_embedding(text)
        if embedding:
            embeddings.append(embedding, provider)
        else:
            embeddings.append([0] * 1536)
            print(f"Failed to generate embedding for chunk {chunk['id']}")
    return embeddings

def store_in_chroma(chunks, embeddings, chroma_path, collection_name='verilog_modules'):
    client_ch = chromadb.PersistentClient(path=chroma_path)
    try:
        client_ch.delete_collection(collection_name)
    except:
        pass
    collection = client_ch.create_collection(collection_name)

    valid_chunks = []
    valid_embeddings = []
    for chunk, emb in zip(chunks, embeddings):
        if not all(x == 0 for x in emb):
            valid_chunks.append(chunk)
            valid_embeddings.append(emb)

    if valid_chunks:
        collection.add(
            embeddings=[emb for emb in valid_embeddings],
            documents=[f"Instruction: {chunk['instruction']}\nCode:\n{chunk['code']}\nSummary:\n{chunk['summary']}" for chunk in valid_chunks],
            metadatas=[{
                'id': uuid.uuid4().hex,
                'instruction': chunk['instruction'],
                'text': chunk['text'],
                'summary': chunk['summary'],
                'row_index': chunk['row_index'],
                'knowledge_graph': chunk['knowledge_graph'],
                'module_name': chunk.get('module_name', '')
            } for chunk in valid_chunks],
            ids=[chunk['id'] for chunk in valid_chunks]
        )