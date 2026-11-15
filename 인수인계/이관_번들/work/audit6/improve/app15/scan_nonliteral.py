"""화면 소스에서 라벨을 만드는 호출 중 역할 인자가 글자 리터럴(또는 조건식 속 리터럴)이 아닌 곳을 찾는다. 사용: python scan_nonliteral.py <작업 폴더>"""
import ast
import sys
from pathlib import Path

root = Path(sys.argv[1])
QT = root / "src" / "chanceblog_desktop" / "ui" / "qt"
LABEL_CALLS = {"UI.label", "UI.Label", "label", "ClampedLabel", "UI.ElidedLabel", "ElidedLabel", "Label"}


def literal_role(node):
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.IfExp):
        return literal_role(node.body) and literal_role(node.orelse)
    return False


for path in sorted(QT.glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def owner(node):
        names = []
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
        return ".".join(reversed(names))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in LABEL_CALLS:
            role = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "role"), None)
            if role is None:
                print("NOROLE", path.name, owner(node), ast.unparse(node)[:90])
            elif not literal_role(role):
                print("NONLIT", path.name, owner(node), ast.unparse(role)[:60], "|", ast.unparse(node)[:100])
