import json
from typing import Callable, Union
from pathlib import Path
import concurrent.futures
from loguru import logger
from .html_to_mdx import html_to_mdx

def js_escape(text: str) -> str:
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace("'", "\\'").replace('\n', ' ')

def render_generic(html: Union[str, list, dict]) -> str:
    if not html:
        return ""
    
    if isinstance(html, str):
        return html_to_mdx(html)
    
    if isinstance(html, list):
        result = []
        for item in html:
            if isinstance(item, dict):
                kind = item.get("kind") or "html"
                content = item.get("content")
                if kind == "html":
                    content = content or ""
                    result.append(html_to_mdx(content))
                elif kind == "example":
                    content = content or {}
                    ex_body = content.get("body", "")
                    result.append(html_to_mdx(ex_body))
            elif isinstance(item, str):
                result.append(html_to_mdx(item))
        return "\n\n".join(result)
        
    return ""

def render_type_table(params: list[dict]) -> str:
    # TODO: Use with future component distribution (and fix component mdx)
    if not params:
        return ""
    
    entries = []
    for param in params:
        name = param["name"]
        
        type_str = " | ".join([t for t in param.get('types', [])])
        
        raw_desc = render_generic(param.get('details', '')).strip()
        desc = js_escape(raw_desc)
        
        fields = []
        fields.append(f"      'description': '{desc}'")
        fields.append(f"      'type': '{type_str}'")
        
        if "default" in param:
            def_val = js_escape(str(param["default"]))
            fields.append(f"      'default': '{def_val}'")
            
        fields_str = ",\n".join(fields)
        
        entries.append(f"    '{name}': {{\n{fields_str}\n    }}")
    
    props = ",\n".join(entries)
    return f"""
<TypeTable
  type={{{{
{props}
  }}}}
/>
"""

def render_params_md(params: list[dict]) -> str:
    if not params:
        return ""

    params_result = []
    for param in params:
        name = param["name"]
        types = " | ".join(param.get("types", [])) or "any"
        description = render_generic(param.get("details", "")).strip()
        default = render_generic(param.get("default") or "")
        default_str = f"Default: {default}" if default != "" else ""
        params_result.append(f"### {name} ({types})\n\n{description}\n\n{default_str}")

    return "\n\n".join(params_result) + "\n"

def render_func(func: dict, heading_level: int = 2) -> str:
    head = "#" * heading_level
    name = func['name']
    path = ".".join(func.get('path', []) + [name])
    
    result = ""
    result += render_generic(func.get("details", "")) + "\n\n"
    
    params_sig = []
    for p in func.get("params", []):
        param = "  " + p['name']
        if p.get('named'):
            param += ":"
            p_types = " | ".join(p.get('types', []))
            param += f" {p_types}"
        params_sig.append(param)

    if func.get("params"):
        result += f"\n{head} Parameters\n\n"
        signature = f"#{path}(\n{',\n'.join(params_sig)}\n)"
        if 'returns' in func:
            signature += f" -> {' '.join(func['returns'])}"
        result += f"```typst\n{signature}\n```\n\n"
        result += render_params_md(func["params"])
        # result += render_type_table(func["params"]) + "\n"

    if func.get("example"):
        result += "\n**Example:**\n"
        ex = func["example"]
        if isinstance(ex, dict) and "body" in ex:
             result += html_to_mdx(ex["body"]) + "\n"
        else:
             result += render_generic(ex) + "\n"

    if func.get("scope"):
        result += f"\n{head}# Definitions\n"
        for scope_func in func["scope"]:
            result += render_func(scope_func, heading_level + 1)

    return result

def get_pages_recursive(json_data: dict, result_list: list, on_item_processed: Callable | None = None) -> None:
    title = json_data.get("title")
    route = json_data.get("route")
    if route:
        route = route.strip("/")

    description = json_data.get("description")
    if description:
        description = description.replace("\n", " ").strip()

    part = json_data.get("part")
    body = json_data.get("body")
    has_children = bool(json_data.get("children"))
    children_order = [elem.get("route").split("/")[-2] for elem in json_data.get("children") or []]
    
    result_list.append({
        "title": title,
        "route": route,
        "description": description,
        "part": part,
        "body": body,
        "has_children": has_children,
        "children_order": children_order
    })

    if on_item_processed:
        on_item_processed(title)

    for children in json_data.get("children", []):
        get_pages_recursive(children, result_list, on_item_processed)

def render_category(category: dict) -> str:
    details = render_generic(category.get("details", ""))

    items = category.get("items", [])

    if not items:
        return details
    
    rows = "\n".join(
        f'    <tr>\n'
        f'      <td width="20px" align="center">—</td>\n'
        f'      <td><code><a href="{item["route"]}">{item["name"]}</a></code></td>\n'
        f'      <td>{item["oneliner"]}</td>\n'
        f'    </tr>'
        for item in items
    )

    table = f"""
<table>
  <thead>
    <tr>
      <th width="20px"></th>
      <th align="left">Name</th>
      <th align="left">Description</th>
    </tr>
  </thead>
  <tbody>
{rows}
  </tbody>
</table>
""".strip()
    return f"{details}\n\n## Definitions\n\n{table}\n"

def render_symbols(symbols: dict) -> str:
    def escape_special_chars(text: str) -> str:
        result = ""
        for character in str(text):
            if character not in ["|", "`", "'", '"', "\\", "{", "}", "<", ">", "-"]:
                result += character
                continue
            result += f"\\{character}"
        return result
    
    result = render_generic(symbols.get('details', ''))
    result += "\n\n"
    result += "| Symbol | Name | Math Class |\n"
    result += "| ----- | ----- | ----- |\n"
    
    for symbol in symbols["list"]:
        value = symbol.get("value") or symbol.get("codepoint")
        math_class = symbol.get("mathClass") or symbol.get("mathShorthand")
        
        result += f"| {escape_special_chars(value)} | {symbol['name']} | {escape_special_chars(math_class)} |\n"
    
    return result

def render_group(group: dict) -> str:
    result = render_generic(group.get("details", "")) + "\n\n"
    for func in group.get("functions", []):
        result += render_func(func)
    return result

def render_type(type_data: dict) -> str:
    result = render_generic(type_data.get("details", "")) + "\n\n"
    
    if type_data.get("constructor"):
        result += "## Constructor\n"
        result += render_func(type_data["constructor"], heading_level=3)
        
    if type_data.get("scope"):
        result += "\n## Methods\n"
        for method in type_data["scope"]:
            result += render_func(method, heading_level=3)
            
    return result

def render_body(body_type: str, body_content) -> str:
    if body_type == "html":
        return render_generic(body_content)
    elif body_type == "category":
        return render_category(body_content)
    elif body_type == "symbols":
        return render_symbols(body_content)
    elif body_type == "func":
        return render_func(body_content)
    elif body_type == "group":
        return render_group(body_content)
    elif body_type == "type":
        return render_type(body_content)
    else:
        logger.warning(f"Skipping unsupported body type: {body_type}")
        return ""

def convert_page_to_mdx(page: dict) -> str:
    title = page.get("title", "Untitled")
    description = (page.get("description") or "").replace('"', '\\"')
    
    body = page.get("body")
    body_content_str = ""

    imports_dict = {
        "<TypeTable": "import { TypeTable } from 'fumadocs-ui/components/type-table';",
        "<TypstPreview": "import { TypstPreview } from '@/components/typst/preview';"
    }
    if body:
        body_type = body.get("kind")
        body_data = body.get("content")
        body_content_str = render_body(body_type, body_data)

    imports = ""
    for import_name in imports_dict.keys():
        if import_name in body_content_str:
            imports += imports_dict[import_name] + "\n"
    if imports:
        imports = "\n" + imports

    content = f"""---
title: "{title}"
description: "{description}"
---\n{imports}
{body_content_str}
"""
    return content


def generate_meta_json(directory_json: dict, folder_path: Path) -> None:
    file_path = folder_path / "meta.json"
    title = directory_json.get("title")
    description = (directory_json.get("description") or "").replace('\n', ' ')
    pages = [f'"{elem}"' for elem in directory_json.get("children_order") or []]
    root_string = ',\n  "root": true' if directory_json.get("root") else ""
    children_order = ', '.join(pages)
    meta = f"""{{
  "title": "{title}",
  "description": "{description}",
  "pages": [{children_order}]{root_string}
}}
"""
    file_path.write_text(meta, encoding='utf-8')

def process_single_page(page: dict, output_base_path: Path):
    try:
        mdx_content = convert_page_to_mdx(page)
        route = page["route"]
        if not route:
            return "ROOT_INDEX", mdx_content, None
            
        elif page["has_children"]:
            folder = output_base_path / route
            folder.mkdir(parents=True, exist_ok=True)
            file_path = folder / "index.mdx"
            
            generate_meta_json(page, folder)
        else:
            folder = output_base_path / route
            folder.parent.mkdir(parents=True, exist_ok=True)
            file_path = Path(str(folder) + ".mdx")
            
        file_path.write_text(mdx_content, encoding='utf-8')
        return "OK", page['title'], None
        
    except Exception as e:
        return "ERROR", page.get('title', 'Unknown'), str(e)

def generate_mdx_docs(input_json: Path, output_path: Path, version: str, is_latest: bool) -> None:
    json_data = json.loads(input_json.read_text(encoding='utf-8'))

    full_pages_list = []
    for item in json_data:
        get_pages_recursive(item, full_pages_list)
    logger.info(f"Found {len(full_pages_list)} pages")

    root_page = next((p for p in full_pages_list if not p["route"]), None)

    title = "latest" if is_latest else f"{version}"
    description = f"Typst Docs for version: {version}"

    if root_page:
        root_data = {
            "title": title,
            "description": description,
            "children_order": [elem.get("route").split("/")[-2] for elem in json_data[1:]],
            "root": "true",
        }
        generate_meta_json(root_data, output_path)
        
        mdx = convert_page_to_mdx(root_page)
        (output_path / "index.mdx").write_text(mdx, encoding='utf-8')
        full_pages_list.remove(root_page)

    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_page = {
            executor.submit(process_single_page, page, output_path): page 
            for page in full_pages_list
        }
        
        for future in concurrent.futures.as_completed(future_to_page):
            status, title, error = future.result()
            if status == "ERROR":
                logger.error(f"Failed to process {title}: {error}")
                
        logger.success(f"Completed MDX generation for {len(full_pages_list) + 1} pages")
