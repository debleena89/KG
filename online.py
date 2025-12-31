import json, urllib, os, argparse
import chromadb
from networkx import Graph
from embed import get_code_embedding
from rdflib import URIRef
from main import LLMClient

def load_chunks_and_chroma_sva(metadata_file, chroma_path, collection_name='verilog_modules'):
    try:
        with open(metadata_file, 'r') as f:
            chunks = json.load(f)
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection(collection_name)
        return chunks, collection
    except Exception as e:
        print(f'Failed to load chunks or Chroma collection: {e}')
        return None, None


def query_vector_db_sva(query_text, collection, provider, n_results=3):
    try:
        query_embedding = get_code_embedding(query_text, provider)
        if query_embedding:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            return results
        else:
            print('Failed to generate query embedding')
            return None
    except Exception as e:
        print(f'Query error: {e}')
        return None

def get_module_info_sva(g, module_name):
    module_uri = URIRef(f"http://example.org/hw#module_{urllib.parse.quote(module_name)}")
    if not any(s == module_uri for s, _, _ in g):
        print(f'No triples found for module {module_name}')
        return None

    input_query = """
    PREFIX ex: <http://example.org/hw#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?signal ?label ?width
    WHERE {
        ex:module_%s ex:hasInput ?signal .
        ?signal rdfs:label ?label .
        OPTIONAL { ?signal ex:width ?width . }
    }
    """ % urllib.parse.quote(module_name)

    output_query = """
    PREFIX ex: <http://example.org/hw#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?signal ?label ?width
    WHERE {
        ex:module_%s ex:hasOutput ?signal .
        ?signal rdfs:label ?label .
        OPTIONAL { ?signal ex:width ?width . }
    }
    """ % urllib.parse.quote(module_name)

    signal_query = """
    PREFIX ex: <http://example.org/hw#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?signal ?label ?width ?type
    WHERE {
        ex:module_%s ex:hasInternalSignal ?signal .
        ?signal rdfs:label ?label .
        OPTIONAL { ?signal ex:width ?width . }
        OPTIONAL { ?signal ex:signalType ?type . }
    }
    """ % urllib.parse.quote(module_name)

    parameter_query = """
    PREFIX ex: <http://example.org/hw#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?param ?label ?value
    WHERE {
        ex:module_%s ex:hasParameter ?param .
        ?param rdfs:label ?label .
        ?param ex:value ?value .
    }
    """ % urllib.parse.quote(module_name)

    operation_query = """
    PREFIX ex: <http://example.org/hw#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?operation ?label ?target ?expression
    WHERE {
        ex:module_%s ex:performsOperation ?operation .
        ?operation rdfs:label ?label .
        ?operation ex:target ?target .
        ?operation ex:hasExpression ?expression .
    }
    """ % urllib.parse.quote(module_name)

    def execute_query(query):
        results = g.query(query)
        output = []
        for row in results:
            row_dict = {}
            for var in results.vars:
                value = row[var]
                row_dict[str(var)] = str(value) if value is not None else None
            output.append(row_dict)
        return output

    try:
        inputs = execute_query(input_query)
        outputs = execute_query(output_query)
        signals = execute_query(signal_query)[:5]
        parameters = execute_query(parameter_query)
        operations = execute_query(operation_query)[:5]
    except Exception as e:
        print(f'Query error: {e}')
        return None

    module_info = {
        'module': module_name,
        'inputs': [{'name': row['label'], 'width': row.get('width', 'unknown')} for row in inputs],
        'outputs': [{'name': row['label'], 'width': row.get('width', 'unknown')} for row in outputs],
        'signals': [{'name': row['label'], 'width': row.get('width', 'unknown'), 'type': row.get('type', 'unknown')} for row in signals],
        'parameters': [{'name': row['label'], 'value': row['value']} for row in parameters],
        'operations': [{'type': row['label'], 'target': row['target'], 'expression': row['expression']} for row in operations]
    }
    return module_info

def construct_llm_prompt_sva(query, results, chunks):
    prompt_template = """
# Verilog Module Generation with Comprehensive Immediate Assertions
**Query**: {query}

**Context**: Relevant Verilog module details to guide the design.

{module_details}

**Task**:
- Generate a standalone, synthesizable Verilog module strictly adhering to the query.
- Ensure 100% syntactically correct Verilog code, compatible with EDA tools.
- Implement all logic directly, no external module instantiations.
- For case statements, define operation codes as `localparam` constants with numeric literals and use these constants in case items.
- Include concise comments for functionality, inputs, outputs, and logic.
- Include comprehensive SystemVerilog immediate assertions (`assert`) covering correctness, bounds, validity, and relationships.
- Output a single code block labeled `Verilog Module with Comprehensive Immediate Assertions`.
"""

    module_details = ''
    max_code_len = 300
    max_summary_len = 100
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        chunk_id = meta['id']
        chunk = next((c for c in chunks if c['chunk_id'] == chunk_id), None)
        if not chunk:
            continue
        kg_file = meta['knowledge_graph']
        g = Graph()
        try:
            g.parse(kg_file, format='turtle')
        except Exception as e:
            print(f'Failed to parse {kg_file}: {e}')
            continue
        module_name = meta['module_name']
        module_info = get_module_info_sva(g, module_name)
        instruction = chunk.get('instruction', meta.get('instruction', 'Unknown'))
        code = chunk.get('code', 'Code not available')
        summary = chunk.get('summary', meta.get('summary', 'Summary not available'))
        code = code[:max_code_len] + ('...' if len(code) > max_code_len else '')
        summary = summary[:max_summary_len] + ('...' if len(summary) > max_summary_len else '')
        module_details += f"Module: {module_name}\nInstruction: {instruction}\nSummary: {summary}\nCode:\n```verilog\n{code}\n```\n"
        if module_info:
            module_details += (
                f"Metadata:\n  Inputs: {json.dumps(module_info['inputs'], indent=2)}\n"
                f"  Outputs: {json.dumps(module_info['outputs'], indent=2)}\n"
                f"  Signals: {json.dumps(module_info['signals'], indent=2)}\n"
                f"  Parameters: {json.dumps(module_info['parameters'], indent=2)}\n"
                f"  Operations: {json.dumps(module_info['operations'], indent=2)}\n"
            )
        module_details += '\n---\n'
    return prompt_template.format(query=query, module_details=module_details)

def call_llm_sva(prompt, client):
    if client.provider == "openai":
        response = client.client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()

    elif client.provider == "google-genai":
        response = client.client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt
        )
        return response.text.strip()

    elif client.provider == "anthropic":
        response = client.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()

def query_llm_sva(query, chunks, collection, client, n_results = 3):
    results = query_vector_db_sva(query, collection, client.provider, n_results)
    if results:
        prompt = construct_llm_prompt_sva(query, results, chunks)
        llm_response = call_llm_sva(prompt, client)
        if llm_response:
            print('\nGenerated Verilog Module with Assertions:\n')
            print(llm_response)
        else:
            print('Failed to get LLM response')
    else:
        print('Failed to query vector database')

def main():
    parser = argparse.ArgumentParser(
        description="Generates SystemVerilog Assertions based on intent using RAG"
    )

    parser.add_argument(
        "--client",
        required=True,
        choices=["openai", "google-genai", "anthropic"],
        help="Which LLM provider to use."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to input Verification Scenario JSON file."
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to output JSON file."
    )

    parser.add_argument(
        "--chroma_dir",
        dest='CHROMA_PERSIST_DIRECTORY',
        help="Path to save chromadb files"
    )

    args = parser.parse_args()
    metadata_file = os.path.join(args.CHROMA_PERSIST_DIRECTORY, 'chunk_metadata.json')
    chroma_path = os.path.join(args.CHROMA_PERSIST_DIRECTORY, 'verilog_chroma_db')
    llm_client = LLMClient(args.client)

    chunks, collection = load_chunks_and_chroma_sva(metadata_file, chroma_path)
    if not chunks or not collection:
        print('Failed to load chunks or Chroma collection')
        return
    print(f'Loaded {len(chunks)} chunks and Chroma collection')

    while True:
        q = input("Query (or 'exit'): ")
        if q.strip().lower() == 'exit':
            break
        query_llm_sva(q, chunks, llm_client, collection)

