import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CodeChunkResult:
    chunk_index: int
    start_line: int
    end_line: int
    chunk_content: str
    content_hash: str
    symbol_name: str | None = None
    symbol_type: str | None = None


class CodeChunker:
    """Semantic and line-aware chunking for repository source files."""

    def __init__(
        self,
        target_lines: int = 60,
        max_lines: int = 120,
        overlap_lines: int = 12,
        max_chunk_chars: int = 4000,
    ):
        self.target_lines = target_lines
        self.max_lines = max_lines
        self.overlap_lines = overlap_lines
        self.max_chunk_chars = max_chunk_chars

        # Semantic boundary regexes
        self.py_def = re.compile(r"^(async\s+def|def)\s+([a-zA-Z0-9_]+)\s*\(")
        self.py_class = re.compile(r"^class\s+([a-zA-Z0-9_]+)")
        self.js_func = re.compile(
            r"^(export\s+)?(async\s+)?function\s+([a-zA-Z0-9_]+)|^(export\s+)?(const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(async\s*)?\("
        )
        self.js_class = re.compile(r"^(export\s+)?class\s+([a-zA-Z0-9_]+)")
        self.go_func = re.compile(r"^func\s+(\([a-zA-Z0-9_\* ]+\)\s+)?([a-zA-Z0-9_]+)\s*\(")
        self.rust_fn = re.compile(r"^(pub\s+)?(async\s+)?fn\s+([a-zA-Z0-9_]+)")
        self.java_method = re.compile(r"^\s*(public|protected|private|static|\s)+[\w<>\[\]]+\s+([a-zA-Z0-9_]+)\s*\(")

    def chunk_file(self, file_path: str, content: str, language: str) -> list[CodeChunkResult]:
        """Split a source file into ordered, deduplicated, retrievable chunks with line references."""
        lines = content.splitlines()
        total_lines = len(lines)

        if total_lines == 0:
            return []

        # If file is small enough to fit in a single chunk, return entire file as one chunk
        if total_lines <= self.target_lines and len(content) <= self.max_chunk_chars:
            ch_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            sym_name = None
            sym_type = "module"
            for line in lines:
                if language == "python":
                    cm = self.py_class.match(line)
                    if cm:
                        sym_name, sym_type = cm.group(1), "class"
                        break
                    dm = self.py_def.match(line)
                    if dm:
                        sym_name, sym_type = dm.group(2), "function"
                        break
                elif language in ("javascript", "typescript"):
                    cm = self.js_class.match(line)
                    if cm:
                        sym_name, sym_type = cm.group(2), "class"
                        break
                    fm = self.js_func.match(line)
                    if fm:
                        sym_name = fm.group(3) or fm.group(6)
                        sym_type = "function"
                        break

            return [
                CodeChunkResult(
                    chunk_index=0,
                    start_line=1,
                    end_line=total_lines,
                    chunk_content=content,
                    content_hash=ch_hash,
                    symbol_name=sym_name,
                    symbol_type=sym_type,
                )
            ]

        # Check for semantic boundaries
        chunks: list[CodeChunkResult] = []
        seen_hashes: set[str] = set()

        if language in ("python", "javascript", "typescript", "go", "rust", "java"):
            chunks = self._chunk_semantic(lines, language)

        # Fallback or supplementary: if semantic chunking produced 0 chunks or left big gaps
        if not chunks:
            chunks = self._chunk_line_window(lines)

        # Filter duplicates and assign sequential chunk_index
        deduped_chunks: list[CodeChunkResult] = []
        for ch in chunks:
            if ch.content_hash in seen_hashes:
                continue
            seen_hashes.add(ch.content_hash)
            deduped_chunks.append(
                CodeChunkResult(
                    chunk_index=len(deduped_chunks),
                    start_line=ch.start_line,
                    end_line=ch.end_line,
                    chunk_content=ch.chunk_content,
                    content_hash=ch.content_hash,
                    symbol_name=ch.symbol_name,
                    symbol_type=ch.symbol_type,
                )
            )

        return deduped_chunks

    def _chunk_semantic(self, lines: list[str], language: str) -> list[CodeChunkResult]:
        """Extract chunks around class, function, and method definitions."""
        total_lines = len(lines)
        chunks: list[CodeChunkResult] = []
        boundaries: list[tuple[int, str, str]] = []  # (line_idx, symbol_name, symbol_type)

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "/*", "*")):
                continue

            if language == "python":
                c_match = self.py_class.match(line)
                if c_match:
                    boundaries.append((idx, c_match.group(1), "class"))
                    continue
                d_match = self.py_def.match(line)
                if d_match:
                    boundaries.append((idx, d_match.group(2), "function"))
                    continue
            elif language in ("javascript", "typescript"):
                c_match = self.js_class.match(line)
                if c_match:
                    boundaries.append((idx, c_match.group(2), "class"))
                    continue
                f_match = self.js_func.match(line)
                if f_match:
                    name = f_match.group(3) or f_match.group(6) or "anonymous"
                    boundaries.append((idx, name, "function"))
                    continue
            elif language == "go":
                g_match = self.go_func.match(line)
                if g_match:
                    boundaries.append((idx, g_match.group(2), "function"))
                    continue
            elif language == "rust":
                r_match = self.rust_fn.match(line)
                if r_match:
                    boundaries.append((idx, r_match.group(3), "function"))
                    continue

        if not boundaries:
            return self._chunk_line_window(lines)

        # Build chunks from boundary markers
        for i, (start_idx, sym_name, sym_type) in enumerate(boundaries):
            next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else total_lines
            # If section is within max_lines, take it
            if next_start - start_idx <= self.max_lines:
                chunk_lines = lines[start_idx:next_start]
                text = "\n".join(chunk_lines).strip()
                if text:
                    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    chunks.append(
                        CodeChunkResult(
                            chunk_index=0,
                            start_line=start_idx + 1,
                            end_line=next_start,
                            chunk_content=text,
                            content_hash=h,
                            symbol_name=sym_name,
                            symbol_type=sym_type,
                        )
                    )
            else:
                # Subdivide large semantic blocks with sliding window
                sub_lines = lines[start_idx:next_start]
                sub_chunks = self._chunk_line_window(
                    sub_lines,
                    line_offset=start_idx,
                    symbol_name=sym_name,
                    symbol_type=sym_type,
                )
                chunks.extend(sub_chunks)

        # If there's header code before the first boundary (e.g. imports, module config)
        if boundaries and boundaries[0][0] > 0:
            head_lines = lines[: boundaries[0][0]]
            head_text = "\n".join(head_lines).strip()
            if head_text and len(head_lines) >= 3:
                h = hashlib.sha256(head_text.encode("utf-8")).hexdigest()
                chunks.insert(
                    0,
                    CodeChunkResult(
                        chunk_index=0,
                        start_line=1,
                        end_line=boundaries[0][0],
                        chunk_content=head_text,
                        content_hash=h,
                        symbol_name=None,
                        symbol_type="header",
                    ),
                )

        return chunks

    def _chunk_line_window(
        self,
        lines: list[str],
        line_offset: int = 0,
        symbol_name: str | None = None,
        symbol_type: str | None = None,
    ) -> list[CodeChunkResult]:
        """Sliding-window chunking by line counts with overlap."""
        total_lines = len(lines)
        chunks: list[CodeChunkResult] = []
        start = 0

        while start < total_lines:
            end = min(start + self.target_lines, total_lines)
            chunk_slice = lines[start:end]
            text = "\n".join(chunk_slice).strip()

            if text:
                h = hashlib.sha256(text.encode("utf-8")).hexdigest()
                chunks.append(
                    CodeChunkResult(
                        chunk_index=0,
                        start_line=line_offset + start + 1,
                        end_line=line_offset + end,
                        chunk_content=text,
                        content_hash=h,
                        symbol_name=symbol_name,
                        symbol_type=symbol_type or "block",
                    )
                )

            if end >= total_lines:
                break
            start += max(1, self.target_lines - self.overlap_lines)

        return chunks
