# Typst Docs to MDX Converter & Translation Pipeline

A tool for automated generation, conversion, and localization of [Typst](https://typst.app) documentation. This project solves the lack of official versioned MDX documentation and provides a robust infrastructure for community translations.

## Key Features

*   **Multi-version Support:** Automatically builds documentation for all Typst versions (starting from `v0.11.0`).
*   **AI-Powered Translation:** Context-aware translation pipeline that preserves terminology and style by using previous translations as a baseline.
*   **MDX & Assets:** Outputs production-ready MDX files and images that ready for web frameworks.

## Architecture

The project consists of several modules connected via Git branches and CI/CD workflows.

![Full project pipeline](assets/pipeline.svg)

### System Components:

1.  **JSON Fetcher:**
    *   Clones Typst source code.
    *   Determines the required Rust version for each historical commit.
    *   Builds `typst-docs` into JSON format.
    *   Structures images (assets) into `dist/assets`.
2.  **Docs Parser:**
    *   Converts raw html JSON into clean MDX.
    *   Injects correct image paths.
3.  **Translator (AI):**
    *   Compares English versions (Old vs New).
    *   Translates only changed text chunks while preserving context from previous translations.
4.  **UI Components:**
    *   Provides ready-to-use React components (e.g., `<TypstPreview />`) for rendering examples.

## Translation Pipeline

> [!WARNING]
> This feature is currently under development.

By combining Git Diff with semantic chunking, token usage is reduced without compromising quality.

![Translation pipeline](assets/translation.svg)

**Core Concept:**
The AI receives three main items as input:
1. `New source chunk` (What needs translation)
2. `Old source chunk` (What it was before)
3. `Old translated chunk` (How we translated it before)

And an optional full context of the new source file.

This allows the model to act as a **smart editor**, applying changes only where the original text has changed, while keeping the human touch from previous translations intact.

## Usage

### Local Development

1.  **Install dependencies:**
    ```
    pip install -r requirements.txt
    ```

2.  **Build documentation JSON files (Fetcher):**
    ```
    python scripts/fetch_json.py
    ```

3. **Convert to MDX (Parser):**
    ```
    python scripts/parse_docs.py
    ```

### Integration (via tiged) - WIP

If you want to use the generated documentation in your website:

```md
# 1. Download content (JSON/MDX)
npx tiged typst-g7-32/typst-mdx#main src/content/docs

# 2. Download assets (Images)
npx tiged typst-g7-32/typst-mdx#raw/assets public/docs-assets

# 3. Download UI components (Optional)
npx tiged typst-g7-32/typst-mdx#ui src/components/typst
```

## Contributing

Translation contributions are welcome!
1.  You can fix translations directly in MDX files in the `i18n` branch.
2.  When a new Typst version is released, AI pipeline will **automatically inherit your fixes** and apply them to the new version.
