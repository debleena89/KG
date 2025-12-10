#!/bin/bash
set -e  # Exit on error

# Folder containing SystemVerilog files
SV_FOLDER="../DATASET/RTL/i2c"

# Where the intermediate JSON dataset will be saved
DATASET_JSON="../RESPONSE/i2c.json"

# Final output after LLM summarization
OUTPUT_JSON="../RESPONSE/i2c_op.json"

# Final TTL after LLM summarization
KNOWLEDGE_FOLDER="../RESPONSE/knowledge_graph"

# LLM provider: openai | google-genai | anthropic
LLM_PROVIDER="google-genai"

# Python scripts
BUILD_SCRIPT="prepare_data.py"
LLM_SCRIPT="main.py"



echo "Building JSON dataset from SystemVerilog files..."
python3 "$BUILD_SCRIPT" \
    --input-folder "$SV_FOLDER" \
    --output "$DATASET_JSON"

echo "Dataset created: $DATASET_JSON"
echo "Running LLM summarizer ($LLM_PROVIDER)..."

python3 "$LLM_SCRIPT" \
    --client "$LLM_PROVIDER" \
    --input "$DATASET_JSON" \
    --output "$OUTPUT_JSON" \
    --files i2c_master_top.sv i2c_master_bit_ctrl.sv i2c_master_byte_ctrl.sv \
    --include_folder "$SV_FOLDER" \
    --kf "$KNOWLEDGE_FOLDER"

echo "All done!"
echo "Output written to: $OUTPUT_JSON"
