class TreesitterManager:
    """Language-aware helpers. Falls back to heuristics when parser is unavailable."""

    def detect_import_lines(self, file_text: str, filetype: str | None = None) -> set[int]:
        _ = filetype
        # Pseudo implementation: in Lua, this will use Treesitter queries first.
        lines = file_text.splitlines()
        import_lines: set[int] = set()

        for idx, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                import_lines.add(idx)
            if s.startswith("require(") or s.startswith("local ") and "require(" in s:
                import_lines.add(idx)

        return import_lines
