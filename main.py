import argparse
import json
import os
from dotenv import load_dotenv
import parse_code
import extract
import openai
from google.genai import Client
import anthropic
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
            credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY missing in .env")
            self.client = Client(vertexai=True, project=project, location=location, credentials=credentials)

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
                model="gemini-2.5-pro",
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

def process_file(input_path, output_path, llm_client):
    with open(input_path, "r") as f:
        rows = json.load(f)

    output_rows = []

    for idx, row in enumerate(rows):
        code = row["code"]

        # LLM Summary
        summary = llm_client.summarize(code)

        output_rows.append({
            "row_number": idx,
            "text": row["text"],
            "code_line_count": len(code),
            "original_code": code,
            "summary": summary
        })

        # Parsing & Knowledge Graph
        module_name, input_ports, output_ports, signals, parameters, operations, ast = \
            parse_code.parse_verilog_code(code)

        modules, signals_dict, param_dict, operation_dict, relationships = \
            extract.extract_entities(
                module_name, input_ports, output_ports, signals,
                parameters, operations, ast
            )

        os.makedirs("knowledge_graphs", exist_ok=True)
        kg_file = os.path.join("knowledge_graphs", f"kg_{idx}.ttl")

        extract.create_knowledge_graph(
            modules, signals_dict, param_dict, operation_dict, relationships, kg_file
        )

    with open(output_path, "w") as f:
        json.dump(output_rows, f, indent=2)

    print(f"Processing completed. Output saved to {output_path}")


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

    args = parser.parse_args()

    llm_client = LLMClient(args.client)
    process_file(args.input, args.output, llm_client)


if __name__ == "__main__":
    main()
