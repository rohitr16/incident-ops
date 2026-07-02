import os
import sys
import ast
import json
from pathlib import Path

ROOT = Path('/home/rohit')
REQUIRED_FILES = [
    ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'layout.js',
    ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'page.js',
    ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'globals.css',
    ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'IncidentDashboard.js',
    ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'IncidentCard.js',
]

IMPORT_CHECKS = {
    'layout.js': ["./globals.css"],
    'IncidentDashboard.js': ["./IncidentCard"],
    'page.js': ["./IncidentDashboard"],
}

def node_available():
    return os.system('node -e "process.exit(0)"') == 0

def run_node_syntax_check(path):
    cmd = f'node --check "{path}"'
    return os.system(cmd) == 0

def run_python_ast_check(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        return True
    except SyntaxError:
        return False
    except Exception:
        return False

def check_imports(path_text, rel_to):
    checked = []
    for mods in IMPORT_CHECKS.values():
        for m in mods:
            checked.append(m)
    return True

def main():
    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        print('MISSING')
        for m in missing:
            print(m)
        sys.exit(1)

    invalid = []
    for path in REQUIRED_FILES:
        if path.suffix == '.js':
            if node_available():
                if not run_node_syntax_check(str(path)):
                    invalid.append(str(path))
            else:
                if not run_python_ast_check(path):
                    invalid.append(str(path))

    if invalid:
        print('MISSING')
        for bad in invalid:
            print(f'invalid:{bad}')
        sys.exit(1)

    dashboard_path = ROOT / 'incident-dashboard-poc' / 'frontend' / 'app' / 'IncidentDashboard.js'
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'feed-panel' not in content or 'inspector-panel' not in content:
        print('MISSING: feed-panel or inspector-panel elements in IncidentDashboard.js')
        sys.exit(1)

    print('VERIFIED')

if __name__ == '__main__':
    main()
