import ast
import glob

def find_unbound(filepath):
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        return
        
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            assigned = set()
            used_before_assignment = set()
            try_blocks = []
            
            class Visitor(ast.NodeVisitor):
                def visit_Name(self, n):
                    if n.id == 'async_session':
                        if isinstance(n.ctx, ast.Store):
                            assigned.add('async_session')
                        elif isinstance(n.ctx, ast.Load):
                            # just to note it's used
                            pass
                    self.generic_visit(n)
                def visit_Try(self, n):
                    self.generic_visit(n)
            
            Visitor().visit(node)
            if 'async_session' in assigned:
                print(f"{filepath}: Function {node.name} assigns 'async_session' locally")

for filepath in glob.glob('backend/app/**/*.py', recursive=True):
    find_unbound(filepath)
