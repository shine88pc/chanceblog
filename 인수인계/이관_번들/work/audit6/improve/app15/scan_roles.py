"""화면 소스에서 라벨의 글자 역할을 쓰는 곳(muted·sub) 목록 — AP15 시험이 못박을 값을 미리 본다. 사용: python scan_roles.py <작업 폴더>"""
import ast
import sys
from pathlib import Path

root = Path(sys.argv[1])
QT = root / "src" / "chanceblog_desktop" / "ui" / "qt"
LABEL_CALLS = {"UI.label", "UI.Label", "label", "ClampedLabel", "UI.ElidedLabel", "ElidedLabel"}


def sites(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def owner(node):
        names = []
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
        return ".".join(reversed(names))

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in LABEL_CALLS:
            role = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "role"), None)
            if role is None:
                continue
            roles = sorted({c.value for c in ast.walk(role) if isinstance(c, ast.Constant) and isinstance(c.value, str)})
            found.append((path.name, owner(node), ast.unparse(node.args[0]) if node.args else "", tuple(roles)))
    return found


for path in sorted(QT.glob("*.py")):
    for site in sites(path):
        if "muted" in site[3] or "sub" in site[3]:
            print(site)
