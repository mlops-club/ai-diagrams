# ai-diagrams

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776ab?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![uv](https://img.shields.io/badge/uv-astral--sh-de5fe9?logo=uv)](https://docs.astral.sh/uv/)
[![Excalidraw](https://img.shields.io/badge/excalidraw-compatible-6965db)](https://excalidraw.com)

<p align="center">
  <img src="pipeline.svg" width="600" alt="mermaid → mermaid2excalidraw.py → excalidraw">
</p>

## Usage

```bash
uv run mermaid2excalidraw.py input.mmd output.excalidraw
```

## Philosophy

Rendering diagrams (SVG, Excalidraw JSON, etc.) with an LLM consumes massive amounts of tokens. The output is dense, coordinate-heavy, and expensive to iterate on. A single Excalidraw diagram can easily be thousands of tokens of raw JSON coordinates.

A smarter approach: **vibe-code a rendering script** that consumes a much simpler input format — Mermaid, D2, PlantUML, CSV, JSON — whatever communicates the minimum information needed. The LLM writes and edits the lightweight source file, and the deterministic script handles all the pixel-pushing.

This is dramatically cheaper and faster to iterate on. Your AI assistant edits a 30-line `.mmd` file instead of a 500-line coordinate dump. The feedback loop tightens from "regenerate the entire diagram" to "tweak one line and re-run."

**Why not just use Mermaid's built-in renderer?** Style and control. Mermaid gives you limited say over aesthetics — you're locked into its layout engine and visual style. By converting to Excalidraw, you get full creative control over colors, spacing, fonts, and that signature hand-drawn look, while keeping the source format dead simple and token-cheap.

## Example

[`naive-storage-flow-pull-storm.mmd`](naive-storage-flow-pull-storm.mmd) → [`naive-storage-flow-pull-storm.excalidraw`](naive-storage-flow-pull-storm.excalidraw)
