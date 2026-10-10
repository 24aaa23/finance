"""Translate searched CASE syntax into the existing, safely interpreted where().

Only conditional syntax is translated. No thresholds, fields or business rules
are invented. The normal expression AST validator still checks the result.
"""
import io
import tokenize


def normalize_expression(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 4096:
        raise ValueError('Expression must be a nonempty string of at most 4096 characters.')
    try:
        tokens = [token for token in tokenize.generate_tokens(io.StringIO(expression).readline)
                  if token.type not in {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                                        tokenize.DEDENT, tokenize.ENDMARKER, tokenize.COMMENT}]
    except (tokenize.TokenError, IndentationError) as error:
        raise ValueError('Malformed conditional expression.') from error
    if not any(token.type == tokenize.NAME and token.string.lower() == 'case' for token in tokens):
        return expression
    index = 0
    converted = False

    def keyword(word):
        return index < len(tokens) and tokens[index].type == tokenize.NAME and tokens[index].string.lower() == word

    def consume(stops, depth):
        nonlocal index, converted
        parts, brackets = [], []
        while index < len(tokens):
            token = tokens[index]
            lower = token.string.lower()
            if not brackets and token.type == tokenize.NAME and lower in stops:
                break
            if (token.type == tokenize.NAME and lower == 'case' and index + 1 < len(tokens)
                    and tokens[index + 1].type == tokenize.NAME and tokens[index + 1].string.lower() == 'when'):
                parts.append(parse_case(depth + 1))
                converted = True
                continue
            if token.string in ('(', '[', '{'):
                brackets.append(token.string)
            elif token.string in (')', ']', '}'):
                if not brackets or {'(': ')', '[': ']', '{': '}'}[brackets.pop()] != token.string:
                    raise ValueError('Unbalanced conditional expression.')
            text = token.string
            if depth and token.type == tokenize.NAME:
                text = {'and': 'and', 'or': 'or', 'not': 'not', 'null': 'null',
                        'true': 'True', 'false': 'False'}.get(lower, text)
            if depth and text == '=':
                text = '=='
            elif depth and text == '<' and index + 1 < len(tokens) and tokens[index + 1].string == '>':
                text = '!='
                index += 1
            parts.append(text)
            index += 1
        if brackets:
            raise ValueError('Unbalanced conditional expression.')
        return ' '.join(parts)

    def parse_case(depth):
        nonlocal index
        if depth > 40:
            raise ValueError('Expression is too deeply nested.')
        index += 1  # CASE
        branches = []
        while keyword('when'):
            index += 1
            condition = consume({'then'}, depth)
            if not condition or not keyword('then'):
                raise ValueError('Searched CASE requires WHEN condition THEN value.')
            index += 1
            value = consume({'when', 'else', 'end'}, depth)
            if not value:
                raise ValueError('Searched CASE has an empty result.')
            branches.append((condition, value))
        if not branches:
            raise ValueError('Only searched CASE WHEN is supported; use where(condition, yes, no).')
        fallback = 'null'
        if keyword('else'):
            index += 1
            fallback = consume({'end'}, depth)
            if not fallback:
                raise ValueError('Searched CASE has an empty ELSE result.')
        if not keyword('end'):
            raise ValueError('Searched CASE requires END.')
        index += 1
        for condition, value in reversed(branches):
            fallback = f'where({condition}, {value}, {fallback})'
        return fallback

    result = consume(set(), 0)
    return result if converted else expression
