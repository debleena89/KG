#!/bin/bash
set -e  # Exit on error

# Where the verification scenarios to be read
DATASET_JSON="../i2c_deep/plan.json"

# Final output after SVA Generation
OUTPUT_JSON="../i2c_deep/assert.json"

# Final TTL after LLM summarization
CHROMA_PERSIST_DIRECTORY="../i2c_deep/chromadb"
# LLM provider: openai | google-genai | anthropic
LLM_PROVIDER="google-genai"

# Python scripts
BUILD_SCRIPT="online.py"

echo "Ask query to generate SVA"

python3 "$BUILD_SCRIPT" \
    --client "$LLM_PROVIDER" \
    --input "$DATASET_JSON" \
    --output "$OUTPUT_JSON" \
    --chroma_dir "$CHROMA_PERSIST_DIRECTORY"

echo "Output written to: $OUTPUT_JSON"
