import argparse
import json
import os
from dotenv import load_dotenv
import parse_code
import extract
import openai
from embed import generate_code_embeddings, store_in_chroma
from google.genai import Client
import anthropic
from google.genai.types import HttpOptions
load_dotenv()

class LLMClient:
    def __init__(self, provider):
        self.provider = provider.lower()

        if self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY missing in .env")
            self.client = openai.OpenAI(api_key=api_key)

        elif self.provider == "google-genai":
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION")
            if not project:
                raise ValueError("GOOGLE_API_KEY missing in .env")
            self.client = Client(vertexai=True, project=project, location=location, http_options=HttpOptions(api_version="v1"))

        elif self.provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY missing in .env")
            self.client = anthropic.Anthropic(api_key=api_key)

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def summarize(self, code):
        prompt = f"""
        Provide a detailed summary of the following Verilog module,
        including its functionality, inputs, outputs, parameters, and key operations.

        Verilog Code:
        ```verilog
        {code}
        ```

        Summary requirements:
        - 100-200 words
        - Purpose of the module
        - Inputs / outputs (with widths)
        - Parameters
        - Main logic / operations
        - Notable features (FSM, sequential, etc.)
        """

        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()

        elif self.provider == "google-genai":
            response = self.client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=prompt
            )
            return response.text.strip()

        elif self.provider == "anthropic":
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

def process_file(input_path, output_path, kf, files, include_folder, llm_client, CHROMA_PERSIST_DIRECTORY):
    chroma_path = os.path.join(CHROMA_PERSIST_DIRECTORY, 'verilog_chroma_db')
    metadata_file = os.path.join(CHROMA_PERSIST_DIRECTORY, 'chunk_metadata.json')
    metadata = []
    with open(input_path, "r") as f:
        rows = json.load(f)

    output_rows = []

    for idx, row in enumerate(rows):
        chunk = {}
        if not any(s in row["text"] for s in files):
            continue
        print(f" Working on {row["text"]}")
        code = row["code"]

        # LLM Summary
        summary = llm_client.summarize(code)

        output_rows.append({
            "row_number": idx,
            "text": row["text"],
            "code_line_count": len(code),
            "code": code,
            "summary": summary
        })

        # Parsing & Knowledge Graph
        module_name, input_ports, output_ports, signals, parameters, operations, ast = \
            parse_code.parse_verilog_code(code, include_folder)

        modules, signals_dict, param_dict, operation_dict, relationships = \
            extract.extract_entities(
                module_name, input_ports, output_ports, signals,
                parameters, operations, ast
            )
        chunk['module_name'] = module_name
        chunk['summary'] = summary
        chunk['knowledge_graph'] = kg_file


        os.makedirs(kf, exist_ok=True)
        kg_file = os.path.join(kf, f"kg_{idx}.ttl")

        extract.create_knowledge_graph(
            modules, 
            signals_dict, 
            param_dict, 
            operation_dict, 
            relationships, 
            kg_file
        )

        metadata.append({
                'row_index':idx,
                'module_name': module_name,
                'knowledge_graph': kg_file,
                'instruction': chunk['instruction'],
                'summary': chunk['summary'],
                'code': chunk['code'],
                'text': row['text']
            })

    with open(output_path, "w") as f:
        json.dump(output_rows, f, indent=2)

    print(f"Processing completed. Output saved to {output_path}")
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f'Metadata saved to {metadata_file}')

    embeddings = generate_code_embeddings(metadata, llm_client)
    print(f'Generated embeddings for {len(embeddings)} chunks')

    store_in_chroma(metadata, embeddings, chroma_path)


def main():
    parser = argparse.ArgumentParser(
        description="Summarize Verilog and generate knowledge graphs using various LLM clients."
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
        help="Path to input JSON file."
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to output JSON file."
    )

    parser.add_argument(
        "--kf",
        required=True,
        help="Path to Knowledge Folder."
    )

    parser.add_argument(
        "--files",
        nargs="*",
        help="Specific .sv/.v files to include (optional)."
    )

    parser.add_argument(
        "--include_folder",
        nargs="*",
        help="Specific folder containing sv/v files"
    )

    parser.add_argument(
        "--chroma_dir",
        dest='CHROMA_PERSIST_DIRECTORY',
        help="Path to save chromadb files"
    )

    args = parser.parse_args()

    llm_client = LLMClient(args.client)
    process_file(args.input, args.output, args.kf, args.files, args.include_folder, llm_client, args.CHROMA_PERSIST_DIRECTORY)


if __name__ == "__main__":
    main()
