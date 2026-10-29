"""Which package registries each source language imports from."""

from __future__ import annotations

# Registries each source language imports from. A KB pattern only counts for a
# file whose language can import from that pattern's registry: `openai` is a
# different package on PyPI, npm and RubyGems.
EXT_ECOSYSTEMS: dict[str, frozenset[str]] = {
    ".py": frozenset({"pypi"}),
    ".go": frozenset({"golang"}),
    ".rs": frozenset({"cargo"}),
    ".java": frozenset({"maven"}),
    ".kt": frozenset({"maven"}),
    ".kts": frozenset({"maven"}),
    ".scala": frozenset({"maven"}),
    ".sc": frozenset({"maven"}),
    ".rb": frozenset({"gem"}),
    ".php": frozenset({"composer"}),
    ".cs": frozenset({"nuget"}),
    ".swift": frozenset({"swift", "github"}),
    **{ext: frozenset({"npm"}) for ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")},
    **{
        ext: frozenset({"conan", "github"})
        for ext in (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx")
    },
}
