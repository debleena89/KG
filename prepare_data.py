import os
import json
import argparse


def load_sv_files(folder_path):
    dataset = []

    sv_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith((".sv", ".v"))
    ]

    for filename in sv_files:
        file_path = os.path.join(folder_path, filename)

        with open(file_path, "r") as f:
            code = f.read()

        text_description = f"SystemVerilog module from file: {filename}"

        dataset.append({
            "text": text_description,
            "code": code
        })

    return dataset


def main():
    parser = argparse.ArgumentParser(
        description="Build a JSON dataset from SystemVerilog files in a folder."
    )

    parser.add_argument(
        "--input-folder",
        required=True,
        help="Folder containing SystemVerilog files."
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Path to output JSON file."
    )

    args = parser.parse_args()

    dataset = load_sv_files(args.input_folder)

    with open(args.output, "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"Dataset created with {len(dataset)} entries → {args.output}")


if __name__ == "__main__":
    main()
