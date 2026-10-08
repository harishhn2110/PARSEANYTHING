"""Semantic Assembly for ParseAnything Atlas.

Reconstructs reading order across multi-column layouts.
Preserves heading hierarchies via parent_id relationships.
Associates captions with figures and charts.
Merges split tables across consecutive pages.
Builds the canonical traceable document Markdown.
"""

from typing import Any

from app.schema import Block, Page


class SemanticAssembler:
    @classmethod
    def assemble(cls, pages: list[Page]) -> tuple[list[Page], str]:
        """Assemble semantic structure across pages and return (assembled_pages, markdown)."""
        if not pages:
            return [], ""

        # 1. Heading hierarchy & Caption-Figure association
        current_heading_id: str | None = None

        for page in pages:
            for b in page.blocks:
                # Heading hierarchy
                if b.type == "heading":
                    current_heading_id = b.id
                elif b.parent_id is None and current_heading_id and b.type not in ("header", "footer"):
                    b.parent_id = current_heading_id

            # Caption association
            figures = [b for b in page.blocks if b.type in ("figure", "chart")]
            captions = [b for b in page.blocks if b.type == "caption"]
            for cap in captions:
                for fig in figures:
                    # If caption is directly below or above figure (within 70 points)
                    y_dist = abs(cap.bbox[1] - fig.bbox[3])
                    if y_dist < 70.0:
                        cap.parent_id = fig.id
                        break

        # 2. Cross-page table merge
        cls._merge_cross_page_tables(pages)

        # 3. Build canonical Markdown
        md_lines: list[str] = []
        for page in pages:
            md_lines.append(f"\n<!-- Page {page.page} -->\n")
            for b in page.blocks:
                if b.type in ("table_row", "table_cell"):
                    # Table rows/cells are rendered within their parent table
                    continue
                if b.type == "header":
                    md_lines.append(f"<!-- [header: {b.id}] {b.content} -->")
                elif b.type == "footer":
                    md_lines.append(f"<!-- [footer: {b.id}] {b.content} -->")
                elif b.type == "heading":
                    md_lines.append(f"\n## {b.content}\n")
                elif b.type == "list":
                    md_lines.append(f"- {b.content}")
                elif b.type == "table":
                    md_lines.append(f"\n{b.content}\n")
                elif b.type == "equation":
                    md_lines.append(f"\n$$\n{b.content}\n$$\n")
                elif b.type == "figure":
                    md_lines.append(f"\n![Figure: {b.id}]({b.content})\n")
                elif b.type == "caption":
                    md_lines.append(f"*{b.content}*\n")
                else:
                    md_lines.append(f"\n{b.content}\n")

        full_markdown = "\n".join(md_lines).strip()
        return pages, full_markdown

    @classmethod
    def _merge_cross_page_tables(cls, pages: list[Page]) -> None:
        """Detect and merge tables split across consecutive pages."""
        for p_idx in range(len(pages) - 1):
            curr_page = pages[p_idx]
            next_page = pages[p_idx + 1]

            # Find tables on curr_page near bottom
            curr_tables = [b for b in curr_page.blocks if b.type == "table"]
            next_tables = [b for b in next_page.blocks if b.type == "table"]

            if not curr_tables or not next_tables:
                continue

            # Check last table of curr_page and first table of next_page
            tbl1 = curr_tables[-1]
            tbl2 = next_tables[0]

            d1 = tbl1.data or {}
            d2 = tbl2.data or {}
            h1 = d1.get("headers", [])
            h2 = d2.get("headers", [])
            r1 = d1.get("rows", [])
            r2 = d2.get("rows", [])

            # Compatible if column count matches
            cols_match = len(h1) > 0 and (len(h1) == len(h2) or (not h2 and r2 and len(r2[0]) == len(h1)))
            headers_repeat = [str(x).strip().lower() for x in h1] == [str(x).strip().lower() for x in h2]

            # Check position proximity (tbl1 ends near bottom, tbl2 starts near top)
            near_boundary = (tbl1.bbox[3] > curr_page.height * 0.55) and (tbl2.bbox[1] < next_page.height * 0.45)

            if cols_match and (headers_repeat or near_boundary):
                # Merge tbl2 rows into tbl1
                combined_rows = list(r1) + list(r2)
                tbl1.data = {
                    "headers": h1,
                    "rows": combined_rows,
                    "merged_from_pages": [curr_page.page, next_page.page],
                }

                # Update markdown representation
                header_line = "| " + " | ".join(h1) + " |"
                sep_line = "| " + " | ".join(["---"] * len(h1)) + " |"
                data_lines = ["| " + " | ".join(r) + " |" for r in combined_rows]
                tbl1.content = "\n".join([header_line, sep_line] + data_lines)

                # Re-parent tbl2 children to tbl1
                for child in next_page.blocks:
                    if child.parent_id == tbl2.id:
                        child.parent_id = tbl1.id

                # Remove tbl2 from next_page.blocks (retain its child rows/cells)
                next_page.blocks = [b for b in next_page.blocks if b.id != tbl2.id]
