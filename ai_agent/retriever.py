from pathlib import Path

class RepositoryRetriever:
    def retrieve(self, repo_path: str, query: str):
        root = Path(repo_path)
        matches = []
        terms = [x.lower() for x in query.replace("?", " ").replace(".", " ").split() if len(x) > 2]
        for p in root.rglob("*"):
            if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
                continue
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue
            score = sum(t in text.lower() for t in terms)
            if score:
                matches.append((score, str(p.relative_to(root)), text[:12000]))
        matches.sort(reverse=True)
        return matches[:8]
