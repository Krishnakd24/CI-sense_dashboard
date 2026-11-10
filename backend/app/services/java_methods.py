# Reused from failing_logs_XMLS/extract_test_code.py; original remains unchanged.
import re

def method_name(name):
    # Keep the complete runtime name in test_name; normalize only source lookup.
    return re.sub(r'\[.*\]$', '', name)


def mask_java(source):
    # Preserve offsets/newlines while hiding comments and string/char literals.
    pattern = r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/'
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def extract_method_code(source, name):
    """Match declarations, not method calls; ignore braces inside strings/comments."""
    masked = mask_java(source)
    pattern = r'(?m)^[ \t]*(?:@[\w.]+\s+)*(?:(?:public|protected|private|static|final|synchronized|abstract|native|default)\s+)*(?:<[^;{}]+>\s+)?[\w.$<>\[\],?]+\s+' + re.escape(name) + r'\s*\([^;{}]*\)\s*(?:throws\s+[\w.,\s]+)?\{'
    matches = list(re.finditer(pattern, masked))
    if len(matches) != 1:
        return None
    match = matches[0]
    start = match.start()
    # Include immediately preceding, single-line annotations.
    while start > 0:
        previous = masked.rfind('\n', 0, max(0, start - 1)) + 1
        if not masked[previous:start].strip().startswith('@'):
            break
        start = previous
    depth = 1
    for end in range(match.end(), len(masked)):
        depth += (masked[end] == '{') - (masked[end] == '}')
        if depth == 0:
            return source[start:end + 1].strip()
    return None
