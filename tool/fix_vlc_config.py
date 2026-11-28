#!/usr/bin/env python3
"""Escape quoted Windows linker paths in VLC 3.x's configure log string."""
import json
from pathlib import Path
import re
import sys


LINE = re.compile(r'(?m)^(#define CONFIGURE_LINE[ \t]+)("[^\n]*")(\r?)$')


def fix(path: Path) -> bool:
    original = path.read_bytes()
    text = original.decode('utf-8')
    match = LINE.search(text)
    if not match:
        raise ValueError('CONFIGURE_LINE definition not found')
    literal = match[2]
    try:
        json.loads(literal)
        return False
    except json.JSONDecodeError:
        # configure already escapes backslashes, but omits double quotes.
        value = literal[1:-1].replace('\\\\', '\\')
    encoded = json.dumps(value, ensure_ascii=True)
    updated = text[:match.start(2)] + encoded + text[match.end(2):]
    path.write_bytes(updated.encode('utf-8'))
    return True


if __name__ == '__main__':
    print('fixed CONFIGURE_LINE' if fix(Path(sys.argv[1])) else 'CONFIGURE_LINE already valid')
