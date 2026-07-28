#!/usr/bin/env python3
"""
Wren Programming Language Interpreter in a single self-contained Python 3 file.
Created for reLang - Language Migration Hackathon.
"""

import sys
import os
import math
import time
import re
import shutil

WREN_VERSION = "0.4.0"

# ==============================================================================
# 1. LEXER / TOKENIZER
# ==============================================================================

class TokenType:
    LEFT_PAREN = "LEFT_PAREN"
    RIGHT_PAREN = "RIGHT_PAREN"
    LEFT_BRACKET = "LEFT_BRACKET"
    RIGHT_BRACKET = "RIGHT_BRACKET"
    LEFT_BRACE = "LEFT_BRACE"
    RIGHT_BRACE = "RIGHT_BRACE"
    COLON = "COLON"
    COMMA = "COMMA"
    DOT = "DOT"
    DOTDOT = "DOTDOT"
    DOTDOTDOT = "DOTDOTDOT"
    SEMICOLON = "SEMICOLON"
    QUESTION = "QUESTION"
    TILDE = "TILDE"
    AMP = "AMP"
    PIPE = "PIPE"
    CARET = "CARET"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    PERCENT = "PERCENT"
    
    BANG = "BANG"
    BANG_EQ = "BANG_EQ"
    EQ = "EQ"
    EQ_EQ = "EQ_EQ"
    GT = "GT"
    GT_EQ = "GT_EQ"
    GT_GT = "GT_GT"
    LT = "LT"
    LT_EQ = "LT_EQ"
    LT_LT = "LT_LT"
    AMP_AMP = "AMP_AMP"
    PIPE_PIPE = "PIPE_PIPE"
    
    IDENTIFIER = "IDENTIFIER"
    FIELD = "FIELD"
    STATIC_FIELD = "STATIC_FIELD"
    STRING = "STRING"
    NUMBER = "NUMBER"
    INTERPOLATION = "INTERPOLATION"
    
    BREAK = "BREAK"
    CLASS = "CLASS"
    CONSTRUCT = "CONSTRUCT"
    CONTINUE = "CONTINUE"
    ELSE = "ELSE"
    FALSE = "FALSE"
    FOR = "FOR"
    FOREIGN = "FOREIGN"
    IF = "IF"
    IMPORT = "IMPORT"
    IN = "IN"
    IS = "IS"
    NULL = "NULL"
    RETURN = "RETURN"
    STATIC = "STATIC"
    SUPER = "SUPER"
    THIS = "THIS"
    TRUE = "TRUE"
    VAR = "VAR"
    WHILE = "WHILE"
    AS = "AS"
    
    NEWLINE = "NEWLINE"
    EOF = "EOF"
    ERROR = "ERROR"

KEYWORDS = {
    "break": TokenType.BREAK,
    "class": TokenType.CLASS,
    "construct": TokenType.CONSTRUCT,
    "continue": TokenType.CONTINUE,
    "else": TokenType.ELSE,
    "false": TokenType.FALSE,
    "for": TokenType.FOR,
    "foreign": TokenType.FOREIGN,
    "if": TokenType.IF,
    "import": TokenType.IMPORT,
    "in": TokenType.IN,
    "is": TokenType.IS,
    "null": TokenType.NULL,
    "return": TokenType.RETURN,
    "static": TokenType.STATIC,
    "super": TokenType.SUPER,
    "this": TokenType.THIS,
    "true": TokenType.TRUE,
    "var": TokenType.VAR,
    "while": TokenType.WHILE,
    "as": TokenType.AS,
}

class Token:
    def __init__(self, type_, text, value, line, column):
        self.type = type_
        self.text = text
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type}, {repr(self.text)}, line={self.line})"

class Lexer:
    def __init__(self, source, filename="<string>"):
        self.source = source
        self.filename = filename
        self.start = 0
        self.current = 0
        self.line = 1
        self.column = 1
        self.start_column = 1
        self.parens = []

    def is_at_end(self):
        return self.current >= len(self.source)

    def advance(self):
        ch = self.source[self.current]
        self.current += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def peek(self):
        if self.is_at_end():
            return '\0'
        return self.source[self.current]

    def peek_next(self):
        if self.current + 1 >= len(self.source):
            return '\0'
        return self.source[self.current + 1]

    def match(self, expected):
        if self.is_at_end() or self.source[self.current] != expected:
            return False
        self.advance()
        return True

    def make_token(self, type_, value=None):
        text = self.source[self.start:self.current]
        return Token(type_, text, value if value is not None else text, self.line, self.start_column)

    def error_token(self, message):
        return Token(TokenType.ERROR, message, message, self.line, self.start_column)

    def scan_tokens(self):
        tokens = []
        while not self.is_at_end():
            token = self.scan_token()
            if token is not None:
                tokens.append(token)
                if token.type == TokenType.ERROR:
                    break
        tokens.append(Token(TokenType.EOF, "", None, self.line, self.column))
        return tokens

    def scan_token(self):
        if self.line == 1 and self.current == 0 and self.source.startswith("#!"):
            while not self.is_at_end() and self.peek() != '\n':
                self.advance()
            return None

        self.start = self.current
        self.start_column = self.column

        c = self.advance()

        if c in ' \r\t':
            return None

        if c == '\n':
            return self.make_token(TokenType.NEWLINE)

        if c == '/':
            if self.match('/'):
                while not self.is_at_end() and self.peek() != '\n':
                    self.advance()
                return None
            elif self.match('*'):
                depth = 1
                while not self.is_at_end() and depth > 0:
                    if self.peek() == '/' and self.peek_next() == '*':
                        self.advance()
                        self.advance()
                        depth += 1
                    elif self.peek() == '*' and self.peek_next() == '/':
                        self.advance()
                        self.advance()
                        depth -= 1
                    else:
                        self.advance()
                if depth > 0:
                    return self.error_token("Unterminated block comment.")
                return None
            else:
                return self.make_token(TokenType.SLASH)

        if c == ')' and self.parens:
            self.parens[-1] -= 1
            if self.parens[-1] == 0:
                self.parens.pop()
                return self.scan_string_continue()
            return self.make_token(TokenType.RIGHT_PAREN)

        if c == '(':
            if self.parens:
                self.parens[-1] += 1
            return self.make_token(TokenType.LEFT_PAREN)

        if c == ')': return self.make_token(TokenType.RIGHT_PAREN)
        if c == '[': return self.make_token(TokenType.LEFT_BRACKET)
        if c == ']': return self.make_token(TokenType.RIGHT_BRACKET)
        if c == '{': return self.make_token(TokenType.LEFT_BRACE)
        if c == '}': return self.make_token(TokenType.RIGHT_BRACE)
        if c == ':': return self.make_token(TokenType.COLON)
        if c == ',': return self.make_token(TokenType.COMMA)
        if c == ';': return self.make_token(TokenType.SEMICOLON)
        if c == '?': return self.make_token(TokenType.QUESTION)
        if c == '~': return self.make_token(TokenType.TILDE)
        if c == '*': return self.make_token(TokenType.STAR)
        if c == '%': return self.make_token(TokenType.PERCENT)

        if c == '+': return self.make_token(TokenType.PLUS)
        if c == '-': return self.make_token(TokenType.MINUS)

        if c == '.':
            if self.match('.'):
                if self.match('.'):
                    return self.make_token(TokenType.DOTDOTDOT)
                return self.make_token(TokenType.DOTDOT)
            return self.make_token(TokenType.DOT)

        if c == '!':
            return self.make_token(TokenType.BANG_EQ if self.match('=') else TokenType.BANG)
        if c == '=':
            return self.make_token(TokenType.EQ_EQ if self.match('=') else TokenType.EQ)
        if c == '<':
            if self.match('='): return self.make_token(TokenType.LT_EQ)
            if self.match('<'): return self.make_token(TokenType.LT_LT)
            return self.make_token(TokenType.LT)
        if c == '>':
            if self.match('='): return self.make_token(TokenType.GT_EQ)
            if self.match('>'): return self.make_token(TokenType.GT_GT)
            return self.make_token(TokenType.GT)
        if c == '&':
            return self.make_token(TokenType.AMP_AMP if self.match('&') else TokenType.AMP)
        if c == '|':
            return self.make_token(TokenType.PIPE_PIPE if self.match('|') else TokenType.PIPE)
        if c == '^': return self.make_token(TokenType.CARET)

        if c == '"':
            if self.peek() == '"' and self.peek_next() == '"':
                self.advance()
                self.advance()
                return self.scan_raw_string()
            return self.scan_string()

        if c.isdigit():
            return self.scan_number(c)

        if c == '_' or c.isalpha():
            return self.scan_identifier(c)

        return self.error_token(f"Invalid character '{c}'.")

    def scan_number(self, first_char):
        if first_char == '0':
            if self.peek() in 'xX':
                self.advance()
                digits = []
                while self.peek().isalnum() and self.peek() in '0123456789abcdefABCDEF':
                    digits.append(self.advance())
                if not digits:
                    return self.error_token("Invalid hex number.")
                val = int("".join(digits), 16)
                return self.make_token(TokenType.NUMBER, float(val))
            elif self.peek() in 'bB':
                self.advance()
                digits = []
                while self.peek() in '01':
                    digits.append(self.advance())
                if not digits:
                    return self.error_token("Invalid binary number.")
                val = int("".join(digits), 2)
                return self.make_token(TokenType.NUMBER, float(val))

        while self.peek().isdigit():
            self.advance()

        if self.peek() == '.' and self.peek_next().isdigit():
            self.advance()
            while self.peek().isdigit():
                self.advance()

        if self.peek() in 'eE':
            self.advance()
            if self.peek() in '+-':
                self.advance()
            if not self.peek().isdigit():
                return self.error_token("Unterminated scientific notation.")
            while self.peek().isdigit():
                self.advance()

        text = self.source[self.start:self.current]
        try:
            val = float(text)
            return self.make_token(TokenType.NUMBER, val)
        except ValueError:
            return self.error_token("Invalid number.")

    def scan_identifier(self, first_char):
        is_field = False
        is_static = False
        if first_char == '_':
            if self.peek() == '_':
                self.advance()
                is_static = True
            else:
                is_field = True

        while self.peek().isalnum() or self.peek() == '_':
            self.advance()

        text = self.source[self.start:self.current]
        if is_static:
            return self.make_token(TokenType.STATIC_FIELD)
        if is_field:
            return self.make_token(TokenType.FIELD)

        type_ = KEYWORDS.get(text, TokenType.IDENTIFIER)
        return self.make_token(type_)

    def scan_raw_string(self):
        val_chars = []
        while not self.is_at_end():
            if self.peek() == '"' and self.peek_next() == '"' and self.current + 2 < len(self.source) and self.source[self.current + 2] == '"':
                self.advance()
                self.advance()
                self.advance()
                return self.make_token(TokenType.STRING, "".join(val_chars))
            val_chars.append(self.advance())
        return self.error_token("Unterminated raw string.")

    def scan_string(self):
        return self._scan_string_internal(is_continue=False)

    def scan_string_continue(self):
        self.start = self.current
        self.start_column = self.column
        return self._scan_string_internal(is_continue=True)

    def _scan_string_internal(self, is_continue=False):
        val_chars = []
        while not self.is_at_end():
            c = self.advance()
            if c == '"':
                return self.make_token(TokenType.STRING, "".join(val_chars))
            elif c == '\n':
                return self.error_token("Unterminated string.")
            elif c == '%':
                if self.peek() == '(':
                    self.advance()
                    self.parens.append(1)
                    return self.make_token(TokenType.INTERPOLATION, "".join(val_chars))
                else:
                    val_chars.append('%')
            elif c == '\\':
                if self.is_at_end():
                    return self.error_token("Unterminated string.")
                escaped = self.advance()
                if escaped == '"': val_chars.append('"')
                elif escaped == '\\': val_chars.append('\\')
                elif escaped == '%': val_chars.append('%')
                elif escaped == '0': val_chars.append('\0')
                elif escaped == 'a': val_chars.append('\a')
                elif escaped == 'b': val_chars.append('\b')
                elif escaped == 'f': val_chars.append('\f')
                elif escaped == 'n': val_chars.append('\n')
                elif escaped == 'r': val_chars.append('\r')
                elif escaped == 't': val_chars.append('\t')
                elif escaped == 'v': val_chars.append('\v')
                elif escaped == 'x':
                    h1 = self.advance() if not self.is_at_end() else ''
                    h2 = self.advance() if not self.is_at_end() else ''
                    if not (re.match(r'[0-9a-fA-F]', h1) and re.match(r'[0-9a-fA-F]', h2)):
                        return self.error_token("Invalid byte escape sequence.")
                    val_chars.append(chr(int(h1 + h2, 16)))
                elif escaped == 'u':
                    hex_str = "".join([self.advance() for _ in range(4) if not self.is_at_end()])
                    if len(hex_str) < 4 or not re.match(r'^[0-9a-fA-F]{4}$', hex_str):
                        return self.error_token("Invalid Unicode escape sequence.")
                    val_chars.append(chr(int(hex_str, 16)))
                elif escaped == 'U':
                    hex_str = "".join([self.advance() for _ in range(8) if not self.is_at_end()])
                    if len(hex_str) < 8 or not re.match(r'^[0-9a-fA-F]{8}$', hex_str):
                        return self.error_token("Invalid Unicode escape sequence.")
                    val_chars.append(chr(int(hex_str, 16)))
                else:
                    return self.error_token(f"Invalid escape character '\\{escaped}'.")
            else:
                val_chars.append(c)

        return self.error_token("Unterminated string.")


# ==============================================================================
# 2. AST NODE DEFINITIONS
# ==============================================================================

class ASTNode: pass
class Expr(ASTNode): pass

class LiteralExpr(Expr):
    def __init__(self, value): self.value = value

class VarExpr(Expr):
    def __init__(self, name): self.name = name

class FieldExpr(Expr):
    def __init__(self, name, is_static):
        self.name = name
        self.is_static = is_static

class AssignExpr(Expr):
    def __init__(self, name, value):
        self.name = name
        self.value = value

class FieldAssignExpr(Expr):
    def __init__(self, name, is_static, value):
        self.name = name
        self.is_static = is_static
        self.value = value

class UnaryExpr(Expr):
    def __init__(self, op, right):
        self.op = op
        self.right = right

class BinaryExpr(Expr):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

class LogicalExpr(Expr):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

class IsExpr(Expr):
    def __init__(self, left, right):
        self.left = left
        self.right = right

class TernaryExpr(Expr):
    def __init__(self, condition, then_branch, else_branch):
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch

class CallExpr(Expr):
    def __init__(self, receiver, name, args, block_arg=None):
        self.receiver = receiver
        self.name = name
        self.args = args
        self.block_arg = block_arg

class SuperCallExpr(Expr):
    def __init__(self, name, args, block_arg=None):
        self.name = name
        self.args = args
        self.block_arg = block_arg

class SubscriptExpr(Expr):
    def __init__(self, receiver, args):
        self.receiver = receiver
        self.args = args

class SubscriptAssignExpr(Expr):
    def __init__(self, receiver, args, value):
        self.receiver = receiver
        self.args = args
        self.value = value

class ListExpr(Expr):
    def __init__(self, elements): self.elements = elements

class MapExpr(Expr):
    def __init__(self, entries): self.entries = entries

class FnExpr(Expr):
    def __init__(self, params, body):
        self.params = params
        self.body = body

class InterpolationExpr(Expr):
    def __init__(self, parts): self.parts = parts

class Stmt(ASTNode): pass

class ExprStmt(Stmt):
    def __init__(self, expr): self.expr = expr

class VarDeclStmt(Stmt):
    def __init__(self, name, initializer):
        self.name = name
        self.initializer = initializer

class BlockStmt(Stmt):
    def __init__(self, statements): self.statements = statements

class IfStmt(Stmt):
    def __init__(self, condition, then_branch, else_branch):
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch

class WhileStmt(Stmt):
    def __init__(self, condition, body):
        self.condition = condition
        self.body = body

class ForStmt(Stmt):
    def __init__(self, variable, sequence, body):
        self.variable = variable
        self.sequence = sequence
        self.body = body

class BreakStmt(Stmt): pass
class ContinueStmt(Stmt): pass

class ReturnStmt(Stmt):
    def __init__(self, value): self.value = value

class ImportVar:
    def __init__(self, name, alias=None):
        self.name = name
        self.alias = alias or name

class ImportStmt(Stmt):
    def __init__(self, path, variables):
        self.path = path
        self.variables = variables

class MethodDeclStmt(ASTNode):
    def __init__(self, name, params, body, is_static, is_foreign, is_construct, signature):
        self.name = name
        self.params = params
        self.body = body
        self.is_static = is_static
        self.is_foreign = is_foreign
        self.is_construct = is_construct
        self.signature = signature

class ClassDeclStmt(Stmt):
    def __init__(self, name, superclass_name, methods, is_foreign=False):
        self.name = name
        self.superclass_name = superclass_name
        self.methods = methods
        self.is_foreign = is_foreign


# ==============================================================================
# 3. PARSER
# ==============================================================================

class ParseError(Exception):
    def __init__(self, message, token):
        super().__init__(message)
        self.message = message
        self.token = token

class Parser:
    def __init__(self, tokens):
        self.tokens = [t for t in tokens if t.type != TokenType.NEWLINE or self.is_significant_newline(t)]
        self.current = 0

    def is_significant_newline(self, token):
        return True

    def is_at_end(self):
        return self.peek().type == TokenType.EOF

    def peek(self):
        return self.tokens[self.current]

    def previous(self):
        return self.tokens[self.current - 1]

    def advance(self):
        if not self.is_at_end():
            self.current += 1
        return self.previous()

    def check(self, type_):
        if self.is_at_end():
            return False
        return self.peek().type == type_

    def match(self, *types):
        for type_ in types:
            if self.check(type_):
                self.advance()
                return True
        return False

    def consume(self, type_, message):
        if self.check(type_):
            return self.advance()
        raise ParseError(message, self.peek())

    def ignore_newlines(self):
        while self.check(TokenType.NEWLINE):
            self.advance()

    def parse(self):
        statements = []
        self.ignore_newlines()
        while not self.is_at_end():
            if self.check(TokenType.ERROR):
                raise ParseError(self.peek().text, self.peek())
            stmt = self.statement()
            if stmt:
                statements.append(stmt)
            self.ignore_newlines()
        return statements

    def statement(self):
        self.ignore_newlines()
        if self.is_at_end():
            return None

        if self.match(TokenType.VAR):
            return self.var_declaration()
        if self.match(TokenType.CLASS) or (self.check(TokenType.FOREIGN) and self.lookahead_is_class()):
            is_foreign = False
            if self.previous().type == TokenType.FOREIGN:
                self.advance()
                is_foreign = True
            return self.class_declaration(is_foreign)
        if self.match(TokenType.IMPORT):
            return self.import_statement()
        if self.match(TokenType.IF):
            return self.if_statement()
        if self.match(TokenType.WHILE):
            return self.while_statement()
        if self.match(TokenType.FOR):
            return self.for_statement()
        if self.match(TokenType.BREAK):
            return BreakStmt()
        if self.match(TokenType.CONTINUE):
            return ContinueStmt()
        if self.match(TokenType.RETURN):
            return self.return_statement()
        if self.check(TokenType.LEFT_BRACE):
            return self.block_statement()

        return self.expression_statement()

    def lookahead_is_class(self):
        return self.current + 1 < len(self.tokens) and self.tokens[self.current + 1].type == TokenType.CLASS

    def var_declaration(self):
        name_token = self.consume(TokenType.IDENTIFIER, "Expect variable name after 'var'.")
        name = name_token.text
        initializer = None
        if self.match(TokenType.EQ):
            initializer = self.expression()
        return VarDeclStmt(name, initializer)

    def class_declaration(self, is_foreign=False):
        name_token = self.consume(TokenType.IDENTIFIER, "Expect class name.")
        superclass = None
        if self.match(TokenType.IS):
            super_token = self.consume(TokenType.IDENTIFIER, "Expect superclass name.")
            superclass = super_token.text

        self.ignore_newlines()
        self.consume(TokenType.LEFT_BRACE, "Expect '{' before class body.")
        self.ignore_newlines()

        methods = []
        while not self.check(TokenType.RIGHT_BRACE) and not self.is_at_end():
            methods.append(self.method_declaration())
            self.ignore_newlines()

        self.consume(TokenType.RIGHT_BRACE, "Expect '}' after class body.")
        return ClassDeclStmt(name_token.text, superclass, methods, is_foreign)

    def method_declaration(self):
        self.ignore_newlines()
        is_foreign = self.match(TokenType.FOREIGN)
        is_static = self.match(TokenType.STATIC)
        is_construct = False

        if not is_static and self.match(TokenType.CONSTRUCT):
            is_construct = True

        name = None
        params = []
        body = None

        if self.check_operator():
            op_token = self.advance()
            name = op_token.text
            if op_token.type in (TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
                                 TokenType.PERCENT, TokenType.LT, TokenType.LT_EQ, TokenType.GT,
                                 TokenType.GT_EQ, TokenType.EQ_EQ, TokenType.BANG_EQ, TokenType.AMP,
                                 TokenType.PIPE, TokenType.CARET, TokenType.LT_LT, TokenType.GT_GT,
                                 TokenType.DOTDOT, TokenType.DOTDOTDOT):
                self.consume(TokenType.LEFT_PAREN, "Expect '(' after operator name.")
                param = self.consume(TokenType.IDENTIFIER, "Expect parameter name.")
                params.append(param.text)
                self.consume(TokenType.RIGHT_PAREN, "Expect ')' after parameter.")
            elif op_token.type in (TokenType.TILDE, TokenType.BANG):
                pass
        elif self.match(TokenType.LEFT_BRACKET):
            name = "[]"
            if not self.check(TokenType.RIGHT_BRACKET):
                while True:
                    p = self.consume(TokenType.IDENTIFIER, "Expect parameter name.")
                    params.append(p.text)
                    if not self.match(TokenType.COMMA):
                        break
            self.consume(TokenType.RIGHT_BRACKET, "Expect ']' after subscript parameters.")
            if self.match(TokenType.EQ):
                name = "[]="
                val_param_name = self.consume(TokenType.IDENTIFIER, "Expect value parameter name.").text
                params.append(val_param_name)
        else:
            name_token = self.consume(TokenType.IDENTIFIER, "Expect method name.")
            name = name_token.text
            if self.match(TokenType.EQ):
                name += "="
                self.consume(TokenType.LEFT_PAREN, "Expect '(' after setter name.")
                val_param = self.consume(TokenType.IDENTIFIER, "Expect setter value parameter name.")
                params.append(val_param.text)
                self.consume(TokenType.RIGHT_PAREN, "Expect ')' after setter parameter.")
            elif self.match(TokenType.LEFT_PAREN):
                if not self.check(TokenType.RIGHT_PAREN):
                    while True:
                        p = self.consume(TokenType.IDENTIFIER, "Expect parameter name.")
                        params.append(p.text)
                        if not self.match(TokenType.COMMA):
                            break
                self.consume(TokenType.RIGHT_PAREN, "Expect ')' after parameters.")

        if not is_foreign:
            self.ignore_newlines()
            self.consume(TokenType.LEFT_BRACE, "Expect '{' before method body.")
            body = self.block_body()
        
        if name in ("[]", "[]="):
            sig = f"{name}({','.join(['_']*len(params))})"
        elif name.endswith("="):
            sig = f"{name}(_)"
        elif params:
            sig = f"{name}({','.join(['_']*len(params))})"
        else:
            sig = name

        return MethodDeclStmt(name, params, body, is_static, is_foreign, is_construct, sig)

    def check_operator(self):
        return self.check_any(TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
                              TokenType.PERCENT, TokenType.LT, TokenType.LT_EQ, TokenType.GT,
                              TokenType.GT_EQ, TokenType.EQ_EQ, TokenType.BANG_EQ, TokenType.AMP,
                              TokenType.PIPE, TokenType.CARET, TokenType.TILDE, TokenType.BANG,
                              TokenType.LT_LT, TokenType.GT_GT, TokenType.DOTDOT, TokenType.DOTDOTDOT)

    def check_any(self, *types):
        return any(self.check(t) for t in types)

    def import_statement(self):
        path_token = self.consume(TokenType.STRING, "Expect module path string after 'import'.")
        variables = []
        if self.match(TokenType.FOR):
            while True:
                name_token = self.consume(TokenType.IDENTIFIER, "Expect variable name in import for list.")
                alias = name_token.text
                if self.match(TokenType.AS):
                    alias = self.consume(TokenType.IDENTIFIER, "Expect alias after 'as'.").text
                variables.append(ImportVar(name_token.text, alias))
                if not self.match(TokenType.COMMA):
                    break
        return ImportStmt(path_token.value, variables)

    def if_statement(self):
        self.consume(TokenType.LEFT_PAREN, "Expect '(' after 'if'.")
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN, "Expect ')' after if condition.")
        then_branch = self.statement()
        else_branch = None
        self.ignore_newlines()
        if self.match(TokenType.ELSE):
            else_branch = self.statement()
        return IfStmt(condition, then_branch, else_branch)

    def while_statement(self):
        self.consume(TokenType.LEFT_PAREN, "Expect '(' after 'while'.")
        condition = self.expression()
        self.consume(TokenType.RIGHT_PAREN, "Expect ')' after while condition.")
        body = self.statement()
        return WhileStmt(condition, body)

    def for_statement(self):
        self.consume(TokenType.LEFT_PAREN, "Expect '(' after 'for'.")
        var_token = self.consume(TokenType.IDENTIFIER, "Expect variable name in 'for'.")
        self.consume(TokenType.IN, "Expect 'in' after variable in 'for'.")
        sequence = self.expression()
        self.consume(TokenType.RIGHT_PAREN, "Expect ')' after 'for' clause.")
        body = self.statement()
        return ForStmt(var_token.text, sequence, body)

    def return_statement(self):
        value = None
        if not self.check(TokenType.NEWLINE) and not self.check(TokenType.SEMICOLON) and not self.check(TokenType.RIGHT_BRACE) and not self.is_at_end():
            value = self.expression()
        return ReturnStmt(value)

    def block_statement(self):
        self.consume(TokenType.LEFT_BRACE, "Expect '{'.")
        return self.block_body()

    def block_body(self):
        statements = []
        self.ignore_newlines()
        while not self.check(TokenType.RIGHT_BRACE) and not self.is_at_end():
            stmt = self.statement()
            if stmt:
                statements.append(stmt)
            self.ignore_newlines()
        self.consume(TokenType.RIGHT_BRACE, "Expect '}' after block.")
        return BlockStmt(statements)

    def expression_statement(self):
        expr = self.expression()
        return ExprStmt(expr)

    def expression(self):
        return self.assignment()

    def assignment(self):
        expr = self.ternary()

        if self.match(TokenType.EQ):
            equals = self.previous()
            value = self.assignment()
            if isinstance(expr, VarExpr):
                return AssignExpr(expr.name, value)
            elif isinstance(expr, FieldExpr):
                return FieldAssignExpr(expr.name, expr.is_static, value)
            elif isinstance(expr, SubscriptExpr):
                return SubscriptAssignExpr(expr.receiver, expr.args, value)
            elif isinstance(expr, CallExpr) and not expr.args and not expr.block_arg:
                return CallExpr(expr.receiver, expr.name + "=", [value])
            raise ParseError("Invalid assignment target.", equals)

        return expr

    def ternary(self):
        expr = self.logic_or()

        if self.match(TokenType.QUESTION):
            then_branch = self.expression()
            self.consume(TokenType.COLON, "Expect ':' in ternary expression.")
            else_branch = self.expression()
            return TernaryExpr(expr, then_branch, else_branch)

        return expr

    def logic_or(self):
        expr = self.logic_and()
        while self.match(TokenType.PIPE_PIPE):
            op = self.previous().text
            right = self.logic_and()
            expr = LogicalExpr(expr, op, right)
        return expr

    def logic_and(self):
        expr = self.is_expr()
        while self.match(TokenType.AMP_AMP):
            op = self.previous().text
            right = self.is_expr()
            expr = LogicalExpr(expr, op, right)
        return expr

    def is_expr(self):
        expr = self.equality()
        while self.match(TokenType.IS):
            right = self.equality()
            expr = IsExpr(expr, right)
        return expr

    def equality(self):
        expr = self.comparison()
        while self.match(TokenType.EQ_EQ, TokenType.BANG_EQ):
            op = self.previous().text
            right = self.comparison()
            expr = BinaryExpr(expr, op, right)
        return expr

    def comparison(self):
        expr = self.bitwise_or()
        while self.match(TokenType.LT, TokenType.LT_EQ, TokenType.GT, TokenType.GT_EQ):
            op = self.previous().text
            right = self.bitwise_or()
            expr = BinaryExpr(expr, op, right)
        return expr

    def bitwise_or(self):
        expr = self.bitwise_xor()
        while self.match(TokenType.PIPE):
            op = self.previous().text
            right = self.bitwise_xor()
            expr = BinaryExpr(expr, op, right)
        return expr

    def bitwise_xor(self):
        expr = self.bitwise_and()
        while self.match(TokenType.CARET):
            op = self.previous().text
            right = self.bitwise_and()
            expr = BinaryExpr(expr, op, right)
        return expr

    def bitwise_and(self):
        expr = self.bitwise_shift()
        while self.match(TokenType.AMP):
            op = self.previous().text
            right = self.bitwise_shift()
            expr = BinaryExpr(expr, op, right)
        return expr

    def bitwise_shift(self):
        expr = self.range_expr()
        while self.match(TokenType.LT_LT, TokenType.GT_GT):
            op = self.previous().text
            right = self.range_expr()
            expr = BinaryExpr(expr, op, right)
        return expr

    def range_expr(self):
        expr = self.term()
        while self.match(TokenType.DOTDOT, TokenType.DOTDOTDOT):
            op = self.previous().text
            right = self.term()
            expr = BinaryExpr(expr, op, right)
        return expr

    def term(self):
        expr = self.factor()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            op = self.previous().text
            right = self.factor()
            expr = BinaryExpr(expr, op, right)
        return expr

    def factor(self):
        expr = self.unary()
        while self.match(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self.previous().text
            right = self.unary()
            expr = BinaryExpr(expr, op, right)
        return expr

    def unary(self):
        if self.match(TokenType.MINUS, TokenType.BANG, TokenType.TILDE):
            op = self.previous().text
            right = self.unary()
            return UnaryExpr(op, right)
        return self.call()

    def call(self):
        expr = self.primary()

        while True:
            if self.match(TokenType.DOT):
                name_token = self.consume(TokenType.IDENTIFIER, "Expect property/method name after '.'.")
                name = name_token.text
                args = []
                block_arg = None
                if self.match(TokenType.LEFT_PAREN):
                    if not self.check(TokenType.RIGHT_PAREN):
                        while True:
                            args.append(self.expression())
                            if not self.match(TokenType.COMMA):
                                break
                    self.consume(TokenType.RIGHT_PAREN, "Expect ')' after arguments.")
                if self.check(TokenType.LEFT_BRACE) or (self.check(TokenType.PIPE) and self.lookahead_is_block()):
                    block_arg = self.block_argument()
                expr = CallExpr(expr, name, args, block_arg)
            elif self.match(TokenType.LEFT_BRACKET):
                args = []
                if not self.check(TokenType.RIGHT_BRACKET):
                    while True:
                        args.append(self.expression())
                        if not self.match(TokenType.COMMA):
                            break
                self.consume(TokenType.RIGHT_BRACKET, "Expect ']' after subscript arguments.")
                expr = SubscriptExpr(expr, args)
            elif self.check(TokenType.LEFT_BRACE) and not isinstance(expr, (CallExpr, VarExpr)):
                break
            else:
                break

        return expr

    def lookahead_is_block(self):
        return True

    def block_argument(self):
        self.ignore_newlines()
        params = []
        if self.match(TokenType.LEFT_BRACE):
            if self.match(TokenType.PIPE):
                if not self.check(TokenType.PIPE):
                    while True:
                        p = self.consume(TokenType.IDENTIFIER, "Expect parameter name in block argument.")
                        params.append(p.text)
                        if not self.match(TokenType.COMMA):
                            break
                self.consume(TokenType.PIPE, "Expect '|' after block parameters.")
            body = self.block_body()
            return FnExpr(params, body)
        return None

    def primary(self):
        if self.match(TokenType.FALSE): return LiteralExpr(False)
        if self.match(TokenType.TRUE): return LiteralExpr(True)
        if self.match(TokenType.NULL): return LiteralExpr(None)
        if self.match(TokenType.NUMBER, TokenType.STRING):
            return LiteralExpr(self.previous().value)

        if self.match(TokenType.INTERPOLATION):
            parts = [LiteralExpr(self.previous().value)]
            while True:
                parts.append(self.expression())
                if self.match(TokenType.INTERPOLATION):
                    parts.append(LiteralExpr(self.previous().value))
                elif self.match(TokenType.STRING):
                    parts.append(LiteralExpr(self.previous().value))
                    break
                else:
                    break
            return InterpolationExpr(parts)

        if self.match(TokenType.THIS):
            return VarExpr("this")

        if self.match(TokenType.SUPER):
            name = None
            if self.match(TokenType.DOT):
                name = self.consume(TokenType.IDENTIFIER, "Expect method name after 'super.'.").text
            args = []
            block_arg = None
            if self.match(TokenType.LEFT_PAREN):
                if not self.check(TokenType.RIGHT_PAREN):
                    while True:
                        args.append(self.expression())
                        if not self.match(TokenType.COMMA):
                            break
                self.consume(TokenType.RIGHT_PAREN, "Expect ')' after super arguments.")
            if self.check(TokenType.LEFT_BRACE):
                block_arg = self.block_argument()
            return SuperCallExpr(name, args, block_arg)

        if self.match(TokenType.FIELD):
            return FieldExpr(self.previous().text, is_static=False)
        if self.match(TokenType.STATIC_FIELD):
            return FieldExpr(self.previous().text, is_static=True)

        if self.match(TokenType.IDENTIFIER):
            return VarExpr(self.previous().text)

        if self.match(TokenType.LEFT_PAREN):
            expr = self.expression()
            self.consume(TokenType.RIGHT_PAREN, "Expect ')' after expression.")
            return expr

        if self.match(TokenType.LEFT_BRACKET):
            elements = []
            self.ignore_newlines()
            if not self.check(TokenType.RIGHT_BRACKET):
                while True:
                    self.ignore_newlines()
                    elements.append(self.expression())
                    self.ignore_newlines()
                    if not self.match(TokenType.COMMA):
                        break
            self.consume(TokenType.RIGHT_BRACKET, "Expect ']' after list elements.")
            return ListExpr(elements)

        if self.match(TokenType.LEFT_BRACE):
            self.ignore_newlines()
            if self.match(TokenType.PIPE):
                params = []
                if not self.check(TokenType.PIPE):
                    while True:
                        p = self.consume(TokenType.IDENTIFIER, "Expect parameter name.")
                        params.append(p.text)
                        if not self.match(TokenType.COMMA):
                            break
                self.consume(TokenType.PIPE, "Expect '|' after block parameters.")
                body = self.block_body()
                return FnExpr(params, body)

            entries = []
            if not self.check(TokenType.RIGHT_BRACE):
                while True:
                    self.ignore_newlines()
                    key = self.expression()
                    self.consume(TokenType.COLON, "Expect ':' after map key.")
                    val = self.expression()
                    entries.append((key, val))
                    self.ignore_newlines()
                    if not self.match(TokenType.COMMA):
                        break
            self.consume(TokenType.RIGHT_BRACE, "Expect '}' after map entries.")
            return MapExpr(entries)

        raise ParseError(f"Unexpected token '{self.peek().text}'.", self.peek())


# ==============================================================================
# 4. RUNTIME OBJECTS & ENVIRONMENT
# ==============================================================================

class WrenError(Exception):
    def __init__(self, message, is_compile_error=False):
        super().__init__(message)
        self.message = message
        self.is_compile_error = is_compile_error

class WrenReturn(Exception):
    def __init__(self, value): self.value = value

class WrenBreak(Exception): pass
class WrenContinue(Exception): pass

class Environment:
    def __init__(self, enclosing=None):
        self.enclosing = enclosing
        self.values = {}

    def define(self, name, value):
        self.values[name] = value

    def assign(self, name, value):
        if name in self.values:
            self.values[name] = value
            return True
        if self.enclosing:
            return self.enclosing.assign(name, value)
        return False

    def get(self, name):
        if name in self.values:
            return self.values[name]
        if self.enclosing:
            return self.enclosing.get(name)
        raise WrenError(f"Undefined variable '{name}'.")

class WrenValue: pass

class WrenClass(WrenValue):
    def __init__(self, name, superclass=None, is_foreign=False):
        self.name = name
        self.superclass = superclass
        self.is_foreign = is_foreign
        self.methods = {}
        self.static_methods = {}
        self.static_fields = {}

    def lookup_method(self, sig):
        if sig in self.methods: return self.methods[sig]
        if self.superclass: return self.superclass.lookup_method(sig)
        return None

    def lookup_static_method(self, sig):
        if sig in self.static_methods: return self.static_methods[sig]
        if self.superclass: return self.superclass.lookup_static_method(sig)
        return None

    def __repr__(self): return f"<class {self.name}>"

class WrenInstance(WrenValue):
    def __init__(self, cls):
        self.cls = cls
        self.fields = {}

    def __repr__(self): return f"instance of {self.cls.name}"

class WrenFn(WrenValue):
    def __init__(self, params, body, closure_env):
        self.params = params
        self.body = body
        self.closure_env = closure_env
        self.arity = len(params)

class WrenFiber(WrenValue):
    INITIAL = "INITIAL"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    DONE = "DONE"
    ERROR = "ERROR"

    def __init__(self, fn):
        self.fn = fn
        self.state = WrenFiber.INITIAL
        self.caller = None
        self.error_val = None
        self.result = None

class WrenList(WrenValue):
    def __init__(self, elements=None):
        self.elements = list(elements) if elements is not None else []

class WrenMap(WrenValue):
    def __init__(self, entries=None):
        self.keys_list = []
        self.values_list = []
        if entries:
            for k, v in entries:
                self.set(k, v)

    def set(self, key, value):
        idx = self._find_key(key)
        if idx != -1:
            self.values_list[idx] = value
        else:
            self.keys_list.append(key)
            self.values_list.append(value)

    def get(self, key):
        idx = self._find_key(key)
        if idx != -1: return self.values_list[idx]
        return None

    def contains(self, key): return self._find_key(key) != -1

    def remove(self, key):
        idx = self._find_key(key)
        if idx != -1:
            val = self.values_list[idx]
            del self.keys_list[idx]
            del self.values_list[idx]
            return val
        return None

    def _find_key(self, key):
        for i, k in enumerate(self.keys_list):
            if wren_equals(k, key): return i
        return -1

class WrenRange(WrenValue):
    def __init__(self, from_val, to_val, is_inclusive):
        self.from_val = from_val
        self.to_val = to_val
        self.is_inclusive = is_inclusive

def wren_equals(a, b):
    if a is b: return True
    if type(a) != type(b): return False
    if isinstance(a, WrenRange):
        return a.from_val == b.from_val and a.to_val == b.to_val and a.is_inclusive == b.is_inclusive
    return a == b


# ==============================================================================
# 5. CORE STANDARD LIBRARY
# ==============================================================================

CORE_CLASSES = {}

class MapEntry:
    def __init__(self, key, value):
        self.key = key
        self.value = value

def init_core_classes():
    global ObjectClass, NullClass, BoolClass, NumClass, StringClass
    global ListClass, MapClass, RangeClass, FnClass, FiberClass, ClassClass
    global SequenceClass, SystemClass, MapEntryClass

    ObjectClass = WrenClass("Object")
    SequenceClass = WrenClass("Sequence", ObjectClass)

    NullClass = WrenClass("Null", ObjectClass)
    BoolClass = WrenClass("Bool", ObjectClass)
    NumClass = WrenClass("Num", ObjectClass)
    StringClass = WrenClass("String", SequenceClass)
    ListClass = WrenClass("List", SequenceClass)
    MapClass = WrenClass("Map", SequenceClass)
    RangeClass = WrenClass("Range", SequenceClass)
    FnClass = WrenClass("Fn", ObjectClass)
    FiberClass = WrenClass("Fiber", ObjectClass)
    ClassClass = WrenClass("Class", ObjectClass)
    SystemClass = WrenClass("System", ObjectClass)
    MapEntryClass = WrenClass("MapEntry", ObjectClass)

    CORE_CLASSES["Object"] = ObjectClass
    CORE_CLASSES["Sequence"] = SequenceClass
    CORE_CLASSES["Null"] = NullClass
    CORE_CLASSES["Bool"] = BoolClass
    CORE_CLASSES["Num"] = NumClass
    CORE_CLASSES["String"] = StringClass
    CORE_CLASSES["List"] = ListClass
    CORE_CLASSES["Map"] = MapClass
    CORE_CLASSES["Range"] = RangeClass
    CORE_CLASSES["Fn"] = FnClass
    CORE_CLASSES["Fiber"] = FiberClass
    CORE_CLASSES["Class"] = ClassClass
    CORE_CLASSES["System"] = SystemClass
    CORE_CLASSES["MapEntry"] = MapEntryClass

    # --- Object methods ---
    bind_native_static(ObjectClass, "same(_,_)", lambda vm, cls, a, b: a is b or wren_equals(a, b))
    bind_native(ObjectClass, "type", lambda vm, this: get_class(this))
    bind_native(ObjectClass, "same(_)", lambda vm, this, other: this is other)
    bind_native(ObjectClass, "toString", lambda vm, this: to_wren_string(this))
    bind_native(ObjectClass, "!()", lambda vm, this: False)
    bind_native(ObjectClass, "==(_)", lambda vm, this, other: this is other or wren_equals(this, other))
    bind_native(ObjectClass, "!=(_)", lambda vm, this, other: not vm.call_method(this, "==(_)", [other]))
    bind_native(ObjectClass, "is(_)", lambda vm, this, cls: is_subclass(get_class(this), cls))
    bind_native(ObjectClass, "===(_)", lambda vm, this, other: is_subclass(get_class(other), this))

    # --- Sequence methods ---
    bind_native(SequenceClass, "all(_)", lambda vm, this, fn: seq_all(vm, this, fn))
    bind_native(SequenceClass, "any(_)", lambda vm, this, fn: seq_any(vm, this, fn))
    bind_native(SequenceClass, "contains(_)", lambda vm, this, val: seq_contains(vm, this, val))
    bind_native(SequenceClass, "count", lambda vm, this: seq_count(vm, this))
    bind_native(SequenceClass, "each(_)", lambda vm, this, fn: seq_each(vm, this, fn))
    bind_native(SequenceClass, "isEmpty", lambda vm, this: seq_is_empty(vm, this))
    bind_native(SequenceClass, "join(_)", lambda vm, this, sep: seq_join(vm, this, sep))
    bind_native(SequenceClass, "toList", lambda vm, this: seq_to_list(vm, this))
    bind_native(SequenceClass, "take(_)", lambda vm, this, num: seq_take(vm, this, num))

    # --- Bool methods ---
    bind_native(BoolClass, "!()", lambda vm, this: not this)
    bind_native(BoolClass, "toString", lambda vm, this: "true" if this else "false")

    # --- Null methods ---
    bind_native(NullClass, "!()", lambda vm, this: True)
    bind_native(NullClass, "toString", lambda vm, this: "null")

    # --- Num methods ---
    bind_native_static(NumClass, "smallest", lambda vm, cls: 2.2250738585072014e-308)
    bind_native_static(NumClass, "largest", lambda vm, cls: 1.7976931348623157e+308)
    bind_native(NumClass, "+(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a + b))
    bind_native(NumClass, "-(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a - b))
    bind_native(NumClass, "*(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a * b))
    bind_native(NumClass, "/(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a / b if b != 0 else (float('nan') if a == 0 else (float('inf') if a > 0 else float('-inf')))))
    bind_native(NumClass, "%(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a % b))
    bind_native(NumClass, "<(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a < b))
    bind_native(NumClass, "<=(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a <= b))
    bind_native(NumClass, ">(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a > b))
    bind_native(NumClass, ">=(_)", lambda vm, this, other: num_op(this, other, lambda a, b: a >= b))
    bind_native(NumClass, "==(_)", lambda vm, this, other: isinstance(other, (int, float)) and this == other)
    bind_native(NumClass, "!=(_)", lambda vm, this, other: not (isinstance(other, (int, float)) and this == other))
    bind_native(NumClass, "-()", lambda vm, this: -this)
    bind_native(NumClass, "~()", lambda vm, this: ~int(this))
    bind_native(NumClass, "&(_)", lambda vm, this, other: int(this) & int(other))
    bind_native(NumClass, "|(_)", lambda vm, this, other: int(this) | int(other))
    bind_native(NumClass, "^(_)", lambda vm, this, other: int(this) ^ int(other))
    bind_native(NumClass, "<<(_)", lambda vm, this, other: int(this) << int(other))
    bind_native(NumClass, ">>(_)", lambda vm, this, other: int(this) >> int(other))
    bind_native(NumClass, "..(_)", lambda vm, this, other: WrenRange(this, check_num(other), True))
    bind_native(NumClass, "...(_)", lambda vm, this, other: WrenRange(this, check_num(other), False))

    bind_native(NumClass, "abs", lambda vm, this: abs(this))
    bind_native(NumClass, "acos", lambda vm, this: math.acos(this))
    bind_native(NumClass, "asin", lambda vm, this: math.asin(this))
    bind_native(NumClass, "atan", lambda vm, this: math.atan(this))
    bind_native(NumClass, "atan2(_)", lambda vm, this, x: math.atan2(this, check_num(x)))
    bind_native(NumClass, "ceil", lambda vm, this: math.ceil(this))
    bind_native(NumClass, "cos", lambda vm, this: math.cos(this))
    bind_native(NumClass, "floor", lambda vm, this: math.floor(this))
    bind_native(NumClass, "fraction", lambda vm, this: math.modf(this)[0])
    bind_native(NumClass, "isInfinity", lambda vm, this: math.isinf(this))
    bind_native(NumClass, "isNan", lambda vm, this: math.isnan(this))
    bind_native(NumClass, "isInteger", lambda vm, this: isinstance(this, int) or (isinstance(this, float) and this.is_integer()))
    bind_native(NumClass, "log", lambda vm, this: math.log(this))
    bind_native(NumClass, "log2", lambda vm, this: math.log2(this))
    bind_native(NumClass, "pow(_)", lambda vm, this, y: math.pow(this, check_num(y)))
    bind_native(NumClass, "round", lambda vm, this: round(this))
    bind_native(NumClass, "sin", lambda vm, this: math.sin(this))
    bind_native(NumClass, "sign", lambda vm, this: -1 if this < 0 else (1 if this > 0 else 0))
    bind_native(NumClass, "sqrt", lambda vm, this: math.sqrt(this) if this >= 0 else float('nan'))
    bind_native(NumClass, "tan", lambda vm, this: math.tan(this))
    bind_native(NumClass, "truncate", lambda vm, this: int(this))
    bind_native(NumClass, "toString", lambda vm, this: format_num(this))

    # --- String methods ---
    bind_native_static(StringClass, "fromCodePoint(_)", lambda vm, cls, cp: chr(int(cp)))
    bind_native_static(StringClass, "fromByte(_)", lambda vm, cls, b: chr(int(b)))
    bind_native(StringClass, "+(_)", lambda vm, this, other: this + check_str(other))
    bind_native(StringClass, "count", lambda vm, this: len(this))
    bind_native(StringClass, "bytes", lambda vm, this: WrenList([b for b in this.encode('latin1', errors='replace')]))
    bind_native(StringClass, "codePoints", lambda vm, this: WrenList([ord(c) for c in this]))
    bind_native(StringClass, "contains(_)", lambda vm, this, sub: check_str(sub) in this)
    bind_native(StringClass, "startsWith(_)", lambda vm, this, sub: this.startswith(check_str(sub)))
    bind_native(StringClass, "endsWith(_)", lambda vm, this, sub: this.endswith(check_str(sub)))
    bind_native(StringClass, "indexOf(_)", lambda vm, this, sub: this.find(check_str(sub)))
    bind_native(StringClass, "replace(_,_)", lambda vm, this, f, t: this.replace(check_str(f), check_str(t)))
    bind_native(StringClass, "split(_)", lambda vm, this, sep: WrenList(this.split(check_str(sep))))
    bind_native(StringClass, "iterate(_)", lambda vm, this, it: string_iterate(this, it))
    bind_native(StringClass, "iteratorValue(_)", lambda vm, this, it: this[int(it)])
    bind_native(StringClass, "[](_)", lambda vm, this, idx: string_subscript(this, idx))
    bind_native(StringClass, "toString", lambda vm, this: this)

    # --- MapEntry methods ---
    bind_native_static(MapEntryClass, "new(_,_)", lambda vm, cls, k, v: MapEntry(k, v))
    bind_native(MapEntryClass, "key", lambda vm, this: this.key)
    bind_native(MapEntryClass, "value", lambda vm, this: this.value)
    bind_native(MapEntryClass, "toString", lambda vm, this: f"{to_wren_string_vm(vm, this.key)}:{to_wren_string_vm(vm, this.value)}")

    # --- List methods ---
    bind_native_static(ListClass, "new", lambda vm, cls: WrenList())
    bind_native_static(ListClass, "filled(_,_)", lambda vm, cls, num, val: WrenList([val] * int(num)))
    bind_native(ListClass, "add(_)", lambda vm, this, val: (this.elements.append(val), val)[1])
    bind_native(ListClass, "clear", lambda vm, this: (this.elements.clear(), None)[1])
    bind_native(ListClass, "count", lambda vm, this: len(this.elements))
    bind_native(ListClass, "isEmpty", lambda vm, this: len(this.elements) == 0)
    bind_native(ListClass, "insert(_,_)", lambda vm, this, idx, val: (this.elements.insert(int(idx), val), val)[1])
    bind_native(ListClass, "iterate(_)", lambda vm, this, iterator: list_iterate(this, iterator))
    bind_native(ListClass, "iteratorValue(_)", lambda vm, this, iterator: this.elements[int(iterator)])
    bind_native(ListClass, "remove(_)", lambda vm, this, val: list_remove(this, val))
    bind_native(ListClass, "removeAt(_)", lambda vm, this, idx: list_remove_at(this, int(idx)))
    bind_native(ListClass, "[](_)", lambda vm, this, idx: list_subscript(this, idx))
    bind_native(ListClass, "[]=(_,_)", lambda vm, this, idx, val: list_subscript_set(this, idx, val))
    bind_native(ListClass, "+(_)", lambda vm, this, other: WrenList(this.elements + check_list(other).elements))
    bind_native(ListClass, "indexOf(_)", lambda vm, this, val: list_index_of(this, val))
    bind_native(ListClass, "contains(_)", lambda vm, this, val: list_index_of(this, val) != -1)
    bind_native(ListClass, "join(_)", lambda vm, this, sep: check_str(sep).join([to_wren_string_vm(vm, x) for x in this.elements]))

    bind_native(ListClass, "map(_)", lambda vm, this, fn: WrenList([vm.call_fn(fn, [x]) for x in this.elements]))
    bind_native(ListClass, "where(_)", lambda vm, this, fn: WrenList([x for x in this.elements if vm.is_truthy(vm.call_fn(fn, [x]))]))
    bind_native(ListClass, "reduce(_)", lambda vm, this, fn: list_reduce_1(vm, this, fn))
    bind_native(ListClass, "reduce(_,_)", lambda vm, this, acc, fn: list_reduce_2(vm, this, acc, fn))
    bind_native(ListClass, "each(_)", lambda vm, this, fn: list_each(vm, this, fn))
    bind_native(ListClass, "toString", lambda vm, this: "[" + ", ".join([to_wren_string_vm(vm, x) for x in this.elements]) + "]")

    # --- Map methods ---
    bind_native_static(MapClass, "new", lambda vm, cls: WrenMap())
    bind_native(MapClass, "[](_)", lambda vm, this, key: map_subscript(this, key))
    bind_native(MapClass, "[]=(_,_)", lambda vm, this, key, val: (this.set(key, val), val)[1])
    bind_native(MapClass, "clear", lambda vm, this: (this.keys_list.clear(), this.values_list.clear(), None)[2])
    bind_native(MapClass, "containsKey(_)", lambda vm, this, key: this.contains(key))
    bind_native(MapClass, "count", lambda vm, this: len(this.keys_list))
    bind_native(MapClass, "isEmpty", lambda vm, this: len(this.keys_list) == 0)
    bind_native(MapClass, "iterate(_)", lambda vm, this, iterator: map_iterate(this, iterator))
    bind_native(MapClass, "iteratorValue(_)", lambda vm, this, iterator: map_iterator_value(this, iterator))
    bind_native(MapClass, "keys", lambda vm, this: WrenList(list(this.keys_list)))
    bind_native(MapClass, "values", lambda vm, this: WrenList(list(this.values_list)))
    bind_native(MapClass, "entries", lambda vm, this: WrenList([MapEntry(k, v) for k, v in zip(this.keys_list, this.values_list)]))
    bind_native(MapClass, "remove(_)", lambda vm, this, key: this.remove(key))
    bind_native(MapClass, "toString", lambda vm, this: "{" + ", ".join([f"{to_wren_string_vm(vm, k)}: {to_wren_string_vm(vm, v)}" for k, v in zip(this.keys_list, this.values_list)]) + "}")

    # --- Range methods ---
    bind_native(RangeClass, "from", lambda vm, this: this.from_val)
    bind_native(RangeClass, "to", lambda vm, this: this.to_val)
    bind_native(RangeClass, "isInclusive", lambda vm, this: this.is_inclusive)
    bind_native(RangeClass, "min", lambda vm, this: min(this.from_val, this.to_val))
    bind_native(RangeClass, "max", lambda vm, this: max(this.from_val, this.to_val))
    bind_native(RangeClass, "iterate(_)", lambda vm, this, iterator: range_iterate(this, iterator))
    bind_native(RangeClass, "iteratorValue(_)", lambda vm, this, iterator: iterator)
    bind_native(RangeClass, "toString", lambda vm, this: f"{format_num(this.from_val)}{'..' if this.is_inclusive else '...'}{format_num(this.to_val)}")

    # --- Fn methods ---
    bind_native(FnClass, "arity", lambda vm, this: this.arity)
    bind_native(FnClass, "call", lambda vm, this: vm.call_fn(this, []))
    bind_native(FnClass, "call(_)", lambda vm, this, a1: vm.call_fn(this, [a1]))
    bind_native(FnClass, "call(_,_)", lambda vm, this, a1, a2: vm.call_fn(this, [a1, a2]))
    bind_native(FnClass, "call(_,_,_)", lambda vm, this, a1, a2, a3: vm.call_fn(this, [a1, a2, a3]))
    bind_native(FnClass, "call(_,_,_,_)", lambda vm, this, a1, a2, a3, a4: vm.call_fn(this, [a1, a2, a3, a4]))
    bind_native_static(FnClass, "new(_)", lambda vm, cls, fn: check_fn(fn))

    # --- Fiber methods ---
    bind_native_static(FiberClass, "new(_)", lambda vm, cls, fn: WrenFiber(check_fn(fn)))
    bind_native_static(FiberClass, "current", lambda vm, cls: vm.current_fiber)
    bind_native_static(FiberClass, "suspend", lambda vm, cls: vm.yield_fiber(None))
    bind_native_static(FiberClass, "yield", lambda vm, cls: vm.yield_fiber(None))
    bind_native_static(FiberClass, "yield(_)", lambda vm, cls, val: vm.yield_fiber(val))
    bind_native_static(FiberClass, "abort(_)", lambda vm, cls, err: vm.abort_fiber(err))
    bind_native(FiberClass, "call", lambda vm, this: vm.run_fiber(this, None, is_try=False))
    bind_native(FiberClass, "call(_)", lambda vm, this, val: vm.run_fiber(this, val, is_try=False))
    bind_native(FiberClass, "try", lambda vm, this: vm.run_fiber(this, None, is_try=True))
    bind_native(FiberClass, "try(_)", lambda vm, this, val: vm.run_fiber(this, val, is_try=True))
    bind_native(FiberClass, "transfer", lambda vm, this: vm.transfer_fiber(this, None, is_error=False))
    bind_native(FiberClass, "transfer(_)", lambda vm, this, val: vm.transfer_fiber(this, val, is_error=False))
    bind_native(FiberClass, "transferError(_)", lambda vm, this, err: vm.transfer_fiber(this, err, is_error=True))
    bind_native(FiberClass, "isDone", lambda vm, this: this.state in (WrenFiber.DONE, WrenFiber.ERROR))
    bind_native(FiberClass, "error", lambda vm, this: this.error_val)

    # --- System methods ---
    bind_native_static(SystemClass, "print", lambda vm, cls: (sys.stdout.write("\n"), sys.stdout.flush(), None)[2])
    bind_native_static(SystemClass, "print(_)", lambda vm, cls, val: (sys.stdout.write(to_wren_string_vm(vm, val) + "\n"), sys.stdout.flush(), None)[2])
    bind_native_static(SystemClass, "write(_)", lambda vm, cls, val: (sys.stdout.write(to_wren_string_vm(vm, val)), sys.stdout.flush(), None)[2])
    bind_native_static(SystemClass, "clock", lambda vm, cls: time.time())
    bind_native_static(SystemClass, "gc", lambda vm, cls: None)

def bind_native(cls, sig, fn): cls.methods[sig] = fn
def bind_native_static(cls, sig, fn): cls.static_methods[sig] = fn

def get_class(val):
    if val is None: return NullClass
    if isinstance(val, bool): return BoolClass
    if isinstance(val, (int, float)): return NumClass
    if isinstance(val, str): return StringClass
    if isinstance(val, WrenList): return ListClass
    if isinstance(val, WrenMap): return MapClass
    if isinstance(val, WrenRange): return RangeClass
    if isinstance(val, WrenFn): return FnClass
    if isinstance(val, WrenFiber): return FiberClass
    if isinstance(val, WrenClass): return ClassClass
    if isinstance(val, MapEntry): return MapEntryClass
    if isinstance(val, WrenInstance): return val.cls
    return ObjectClass

def is_subclass(sub, super_):
    curr = sub
    while curr:
        if curr is super_: return True
        curr = curr.superclass
    return False

def check_num(val):
    if not isinstance(val, (int, float)): raise WrenError("Right operand must be a number.")
    return val

def check_str(val):
    if not isinstance(val, str): raise WrenError("Argument must be a string.")
    return val

def check_list(val):
    if not isinstance(val, WrenList): raise WrenError("Argument must be a list.")
    return val

def check_fn(val):
    if not isinstance(val, WrenFn): raise WrenError("Argument must be a function.")
    return val

def num_op(a, b, op):
    if not isinstance(b, (int, float)): raise WrenError("Right operand must be a number.")
    return op(a, b)

def format_num(val):
    if isinstance(val, int): return str(val)
    if isinstance(val, float):
        if math.isnan(val): return "nan"
        if math.isinf(val): return "infinity" if val > 0 else "-infinity"
        if val.is_integer(): return str(int(val))
        return f"{val:.14g}"
    return str(val)

def to_wren_string(val):
    if val is None: return "null"
    if isinstance(val, bool): return "true" if val else "false"
    if isinstance(val, (int, float)): return format_num(val)
    if isinstance(val, str): return val
    if isinstance(val, WrenRange): return f"{format_num(val.from_val)}{'..' if val.is_inclusive else '...'}{format_num(val.to_val)}"
    if isinstance(val, WrenClass): return val.name
    if isinstance(val, MapEntry): return f"{to_wren_string(val.key)}:{to_wren_string(val.value)}"
    if isinstance(val, WrenInstance): return f"instance of {val.cls.name}"
    return str(val)

def to_wren_string_vm(vm, val):
    if isinstance(val, (str, bool, int, float)) or val is None: return to_wren_string(val)
    try:
        return str(vm.call_method(val, "toString", []))
    except Exception:
        return to_wren_string(val)

def string_iterate(s, it):
    if it is None: return 0 if s else False
    if isinstance(it, (int, float)):
        i = int(it) + 1
        return i if i < len(s) else False
    return False

def string_subscript(s, idx):
    if isinstance(idx, (int, float)):
        i = int(idx)
        if i < 0: i += len(s)
        if 0 <= i < len(s): return s[i]
        raise WrenError("Subscript out of bounds.")
    elif isinstance(idx, WrenRange):
        f = int(idx.from_val)
        t = int(idx.to_val)
        if f < 0: f += len(s)
        if t < 0: t += len(s)
        end = t + 1 if idx.is_inclusive else t
        return s[f:end]
    raise WrenError("Subscript must be a number or range.")

def list_subscript(l, idx):
    if isinstance(idx, (int, float)):
        i = int(idx)
        if i < 0: i += len(l.elements)
        if 0 <= i < len(l.elements): return l.elements[i]
        raise WrenError("Subscript out of bounds.")
    elif isinstance(idx, WrenRange):
        f = int(idx.from_val)
        t = int(idx.to_val)
        if f < 0: f += len(l.elements)
        if t < 0: t += len(l.elements)
        end = t + 1 if idx.is_inclusive else t
        return WrenList(l.elements[f:end])
    raise WrenError("Subscript must be a number or range.")

def list_subscript_set(l, idx, val):
    if isinstance(idx, (int, float)):
        i = int(idx)
        if i < 0: i += len(l.elements)
        if 0 <= i < len(l.elements):
            l.elements[i] = val
            return val
        raise WrenError("Subscript out of bounds.")
    raise WrenError("Subscript must be a number.")

def list_iterate(l, iterator):
    if iterator is None: return 0 if l.elements else False
    if isinstance(iterator, (int, float)):
        i = int(iterator) + 1
        return i if i < len(l.elements) else False
    return False

def list_remove(l, val):
    for i, elem in enumerate(l.elements):
        if wren_equals(elem, val):
            del l.elements[i]
            return val
    return None

def list_remove_at(l, idx):
    if 0 <= idx < len(l.elements): return l.elements.pop(idx)
    raise WrenError("Index out of bounds.")

def list_index_of(l, val):
    for i, elem in enumerate(l.elements):
        if wren_equals(elem, val): return i
    return -1

def list_reduce_1(vm, l, fn):
    if not l.elements: raise WrenError("Cannot reduce an empty list.")
    acc = l.elements[0]
    for elem in l.elements[1:]:
        acc = vm.call_fn(fn, [acc, elem])
    return acc

def list_reduce_2(vm, l, acc, fn):
    for elem in l.elements:
        acc = vm.call_fn(fn, [acc, elem])
    return acc

def list_each(vm, l, fn):
    for elem in l.elements:
        vm.call_fn(fn, [elem])
    return None

def seq_all(vm, seq, fn):
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        if not vm.is_truthy(vm.call_fn(fn, [val])): return False
        it = vm.call_method(seq, "iterate(_)", [it])
    return True

def seq_any(vm, seq, fn):
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        if vm.is_truthy(vm.call_fn(fn, [val])): return True
        it = vm.call_method(seq, "iterate(_)", [it])
    return False

def seq_contains(vm, seq, search_val):
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        if wren_equals(val, search_val): return True
        it = vm.call_method(seq, "iterate(_)", [it])
    return False

def seq_count(vm, seq):
    count = 0
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        count += 1
        it = vm.call_method(seq, "iterate(_)", [it])
    return count

def seq_each(vm, seq, fn):
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        vm.call_fn(fn, [val])
        it = vm.call_method(seq, "iterate(_)", [it])
    return None

def seq_is_empty(vm, seq):
    it = vm.call_method(seq, "iterate(_)", [None])
    return not vm.is_truthy(it)

def seq_join(vm, seq, sep):
    parts = []
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        parts.append(to_wren_string_vm(vm, val))
        it = vm.call_method(seq, "iterate(_)", [it])
    return check_str(sep).join(parts)

def seq_to_list(vm, seq):
    elems = []
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it):
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        elems.append(val)
        it = vm.call_method(seq, "iterate(_)", [it])
    return WrenList(elems)

def seq_take(vm, seq, count):
    n = int(count)
    elems = []
    it = vm.call_method(seq, "iterate(_)", [None])
    while vm.is_truthy(it) and len(elems) < n:
        val = vm.call_method(seq, "iteratorValue(_)", [it])
        elems.append(val)
        it = vm.call_method(seq, "iterate(_)", [it])
    return WrenList(elems)

def map_subscript(m, key): return m.get(key)

def map_iterate(m, iterator):
    if iterator is None: return 0 if m.keys_list else False
    if isinstance(iterator, (int, float)):
        i = int(iterator) + 1
        return i if i < len(m.keys_list) else False
    return False

def map_iterator_value(m, iterator):
    i = int(iterator)
    return MapEntry(m.keys_list[i], m.values_list[i])

def range_iterate(r, iterator):
    if iterator is None: return r.from_val
    if isinstance(iterator, (int, float)):
        curr = int(iterator)
        if r.from_val <= r.to_val:
            next_val = curr + 1
            if r.is_inclusive:
                return next_val if next_val <= r.to_val else False
            else:
                return next_val if next_val < r.to_val else False
        else:
            next_val = curr - 1
            if r.is_inclusive:
                return next_val if next_val >= r.to_val else False
            else:
                return next_val if next_val > r.to_val else False
    return False

init_core_classes()


# ==============================================================================
# 6. BUILTIN MODULES
# ==============================================================================

def register_builtin_modules(interpreter):
    os_class_platform = WrenClass("Platform")
    bind_native_static(os_class_platform, "homePath", lambda vm, cls: os.path.expanduser("~"))
    bind_native_static(os_class_platform, "isPosix", lambda vm, cls: os.name != 'nt')
    bind_native_static(os_class_platform, "name", lambda vm, cls: "Windows" if os.name == 'nt' else "Posix")

    os_class_process = WrenClass("Process")
    bind_native_static(os_class_process, "allArguments", lambda vm, cls: WrenList(sys.argv))
    bind_native_static(os_class_process, "cwd", lambda vm, cls: os.getcwd())
    bind_native_static(os_class_process, "pid", lambda vm, cls: os.getpid())
    bind_native_static(os_class_process, "ppid", lambda vm, cls: getattr(os, 'getppid', lambda: 0)())
    bind_native_static(os_class_process, "version", lambda vm, cls: "0.4.0")

    interpreter.modules["os"] = {
        "Platform": os_class_platform,
        "Process": os_class_process
    }

    io_class_directory = WrenClass("Directory")
    bind_native_static(io_class_directory, "create_(_,_)", lambda vm, cls, path, fiber: (os.makedirs(path, exist_ok=True), None)[1])
    bind_native_static(io_class_directory, "delete_(_,_)", lambda vm, cls, path, fiber: (shutil.rmtree(path) if os.path.isdir(path) else os.remove(path), None)[1])
    bind_native_static(io_class_directory, "list_(_,_)", lambda vm, cls, path, fiber: WrenList(os.listdir(path)))

    io_class_file = WrenClass("File")
    bind_native_static(io_class_file, "realPath_(_,_)", lambda vm, cls, path, fiber: os.path.realpath(path))
    bind_native_static(io_class_file, "sizePath_(_,_)", lambda vm, cls, path, fiber: os.path.getsize(path))

    io_class_stat = WrenClass("Stat")
    bind_native_static(io_class_stat, "path_(_,_)", lambda vm, cls, path, fiber: create_stat_instance(path))

    interpreter.modules["io"] = {
        "Directory": io_class_directory,
        "File": io_class_file,
        "Stat": io_class_stat
    }

    scheduler_class = WrenClass("Scheduler")
    bind_native_static(scheduler_class, "captureMethods_()", lambda vm, cls: None)
    interpreter.modules["scheduler"] = {"Scheduler": scheduler_class}

    timer_class = WrenClass("Timer")
    bind_native_static(timer_class, "startTimer_(_,_)", lambda vm, cls, ms, fiber: (time.sleep(ms / 1000.0), None)[1])
    interpreter.modules["timer"] = {"Timer": timer_class}

def create_stat_instance(path):
    stat_cls = WrenClass("Stat")
    inst = WrenInstance(stat_cls)
    if os.path.exists(path):
        st = os.stat(path)
        inst.fields["isFile"] = os.path.isfile(path)
        inst.fields["isDirectory"] = os.path.isdir(path)
        inst.fields["size"] = st.st_size
    else:
        return None
    return inst


# ==============================================================================
# 7. INTERPRETER EXECUTION ENGINE
# ==============================================================================

class Interpreter:
    def __init__(self, root_dir="."):
        self.root_dir = root_dir
        self.globals = Environment()
        self.environment = self.globals
        self.current_class = None
        self.current_instance = None
        self.current_fiber = None
        self.modules = {}

        for name, cls in CORE_CLASSES.items():
            self.globals.define(name, cls)

        self.main_fiber = WrenFiber(None)
        self.main_fiber.state = WrenFiber.RUNNING
        self.current_fiber = self.main_fiber

    def interpret(self, statements):
        last_val = None
        for stmt in statements:
            last_val = self.execute(stmt)
        return last_val

    def execute(self, stmt):
        if isinstance(stmt, ExprStmt):
            return self.evaluate(stmt.expr)
        elif isinstance(stmt, VarDeclStmt):
            val = self.evaluate(stmt.initializer) if stmt.initializer else None
            self.environment.define(stmt.name, val)
            return val
        elif isinstance(stmt, BlockStmt):
            return self.execute_block(stmt.statements, Environment(self.environment))
        elif isinstance(stmt, IfStmt):
            cond = self.evaluate(stmt.condition)
            if self.is_truthy(cond):
                return self.execute(stmt.then_branch)
            elif stmt.else_branch:
                return self.execute(stmt.else_branch)
            return None
        elif isinstance(stmt, WhileStmt):
            while self.is_truthy(self.evaluate(stmt.condition)):
                try:
                    self.execute(stmt.body)
                except WrenBreak:
                    break
                except WrenContinue:
                    continue
            return None
        elif isinstance(stmt, ForStmt):
            seq = self.evaluate(stmt.sequence)
            iterator = self.call_method(seq, "iterate(_)", [None])
            while self.is_truthy(iterator):
                val = self.call_method(seq, "iteratorValue(_)", [iterator])
                loop_env = Environment(self.environment)
                loop_env.define(stmt.variable, val)
                try:
                    self.execute_block([stmt.body] if not isinstance(stmt.body, BlockStmt) else stmt.body.statements, loop_env)
                except WrenBreak:
                    break
                except WrenContinue:
                    pass
                iterator = self.call_method(seq, "iterate(_)", [iterator])
            return None
        elif isinstance(stmt, BreakStmt):
            raise WrenBreak()
        elif isinstance(stmt, ContinueStmt):
            raise WrenContinue()
        elif isinstance(stmt, ReturnStmt):
            val = self.evaluate(stmt.value) if stmt.value else None
            raise WrenReturn(val)
        elif isinstance(stmt, ImportStmt):
            self.execute_import(stmt)
            return None
        elif isinstance(stmt, ClassDeclStmt):
            self.execute_class_decl(stmt)
            return None
        raise WrenError(f"Unknown statement type: {type(stmt)}")

    def execute_block(self, statements, environment):
        previous = self.environment
        try:
            self.environment = environment
            for stmt in statements:
                self.execute(stmt)
        finally:
            self.environment = previous

    def execute_class_decl(self, stmt):
        superclass = CORE_CLASSES["Object"]
        if stmt.superclass_name:
            superclass = self.environment.get(stmt.superclass_name)
            if not isinstance(superclass, WrenClass):
                raise WrenError("Superclass must be a class.")

        cls = WrenClass(stmt.name, superclass, stmt.is_foreign)
        self.environment.define(stmt.name, cls)

        for m in stmt.methods:
            if m.is_static:
                cls.static_methods[m.signature] = m
            else:
                cls.methods[m.signature] = m

    def execute_import(self, stmt):
        path = stmt.path
        if not path.endswith(".wren"):
            path_file = path + ".wren"
        else:
            path_file = path

        full_path = os.path.normpath(os.path.join(self.root_dir, path_file))
        if not os.path.exists(full_path):
            full_path = os.path.normpath(os.path.join(self.root_dir, "wren_modules", path_file))

        if full_path in self.modules:
            mod_env = self.modules[full_path]
        else:
            if not os.path.exists(full_path):
                raise WrenError(f"Could not find module '{stmt.path}'.")
            with open(full_path, "r", encoding="utf-8") as f:
                source = f.read()

            lexer = Lexer(source, full_path)
            tokens = lexer.scan_tokens()
            parser = Parser(tokens)
            ast_stmts = parser.parse()

            mod_env = Environment(self.globals)
            prev_env = self.environment
            try:
                self.environment = mod_env
                for s in ast_stmts:
                    self.execute(s)
            finally:
                self.environment = prev_env
            self.modules[full_path] = mod_env

        for var in stmt.variables:
            val = mod_env.get(var.name)
            self.environment.define(var.alias, val)

    def evaluate(self, expr):
        if isinstance(expr, LiteralExpr):
            return expr.value
        elif isinstance(expr, VarExpr):
            if expr.name == "this":
                if self.current_instance is not None:
                    return self.current_instance
                elif self.current_class is not None:
                    return self.current_class
                raise WrenError("Cannot use 'this' outside of a method.")
            return self.environment.get(expr.name)
        elif isinstance(expr, FieldExpr):
            if expr.is_static:
                if not self.current_class:
                    raise WrenError("Cannot access static field outside of class.")
                return self.current_class.static_fields.get(expr.name, None)
            else:
                if not isinstance(self.current_instance, WrenInstance):
                    raise WrenError("Cannot access instance field outside of instance method.")
                return self.current_instance.fields.get(expr.name, None)
        elif isinstance(expr, AssignExpr):
            val = self.evaluate(expr.value)
            if not self.environment.assign(expr.name, val):
                self.environment.define(expr.name, val)
            return val
        elif isinstance(expr, FieldAssignExpr):
            val = self.evaluate(expr.value)
            if expr.is_static:
                if not self.current_class:
                    raise WrenError("Cannot assign static field outside of class.")
                self.current_class.static_fields[expr.name] = val
            else:
                if not isinstance(self.current_instance, WrenInstance):
                    raise WrenError("Cannot assign instance field outside of instance method.")
                self.current_instance.fields[expr.name] = val
            return val
        elif isinstance(expr, UnaryExpr):
            right = self.evaluate(expr.right)
            sig = f"{expr.op}()"
            return self.call_method(right, sig, [])
        elif isinstance(expr, BinaryExpr):
            left = self.evaluate(expr.left)
            right = self.evaluate(expr.right)
            sig = f"{expr.op}(_)"
            return self.call_method(left, sig, [right])
        elif isinstance(expr, LogicalExpr):
            left = self.evaluate(expr.left)
            if expr.op == "||":
                if self.is_truthy(left): return left
                return self.evaluate(expr.right)
            elif expr.op == "&&":
                if not self.is_truthy(left): return left
                return self.evaluate(expr.right)
        elif isinstance(expr, IsExpr):
            left = self.evaluate(expr.left)
            right = self.evaluate(expr.right)
            if not isinstance(right, WrenClass):
                raise WrenError("Right operand of 'is' must be a class.")
            return is_subclass(get_class(left), right)
        elif isinstance(expr, TernaryExpr):
            cond = self.evaluate(expr.condition)
            if self.is_truthy(cond):
                return self.evaluate(expr.then_branch)
            return self.evaluate(expr.else_branch)
        elif isinstance(expr, CallExpr):
            receiver = self.evaluate(expr.receiver) if expr.receiver else None
            args = [self.evaluate(a) for a in expr.args]
            if expr.block_arg:
                fn_val = self.evaluate(expr.block_arg)
                args.append(fn_val)
            sig = self.build_signature(expr.name, len(args))
            return self.call_method(receiver, sig, args)
        elif isinstance(expr, SuperCallExpr):
            args = [self.evaluate(a) for a in expr.args]
            if expr.block_arg:
                args.append(self.evaluate(expr.block_arg))
            name = expr.name or "new"
            sig = self.build_signature(name, len(args))
            if not self.current_class or not self.current_class.superclass:
                raise WrenError("Cannot call 'super' outside of inherited class method.")
            return self.call_method_class(self.current_class.superclass, self.current_instance, sig, args)
        elif isinstance(expr, SubscriptExpr):
            receiver = self.evaluate(expr.receiver)
            args = [self.evaluate(a) for a in expr.args]
            sig = f"[]({''.join(['_']*len(args))})" if len(args) == 1 else f"[]({','.join(['_']*len(args))})"
            return self.call_method(receiver, sig, args)
        elif isinstance(expr, SubscriptAssignExpr):
            receiver = self.evaluate(expr.receiver)
            args = [self.evaluate(a) for a in expr.args]
            val = self.evaluate(expr.value)
            args.append(val)
            sig = f"[]=({','.join(['_']*len(args))})"
            return self.call_method(receiver, sig, args)
        elif isinstance(expr, ListExpr):
            elems = [self.evaluate(e) for e in expr.elements]
            return WrenList(elems)
        elif isinstance(expr, MapExpr):
            entries = [(self.evaluate(k), self.evaluate(v)) for k, v in expr.entries]
            return WrenMap(entries)
        elif isinstance(expr, FnExpr):
            return WrenFn(expr.params, expr.body, self.environment)
        elif isinstance(expr, InterpolationExpr):
            parts = [to_wren_string_vm(self, self.evaluate(p)) for p in expr.parts]
            return "".join(parts)
        raise WrenError(f"Unknown expression type: {type(expr)}")

    def is_truthy(self, val):
        if val is None or val is False:
            return False
        return True

    def build_signature(self, name, arg_count):
        if name.endswith("="):
            base = name[:-1]
            return f"{base}=(_)"
        if arg_count == 0:
            return name
        return f"{name}({','.join(['_']*arg_count)})"

    def call_method(self, receiver, sig, args):
        cls = get_class(receiver)
        if isinstance(receiver, WrenClass):
            method = receiver.lookup_static_method(sig)
            if not method:
                method = cls.lookup_method(sig)
            if method:
                return self.invoke_method(method, receiver, receiver, args)
            if sig == "new" or sig.startswith("new") or sig in receiver.static_methods or sig in receiver.methods:
                instance = WrenInstance(receiver)
                construct_method = receiver.lookup_method(sig)
                if construct_method:
                    self.invoke_method(construct_method, instance, instance, args)
                return instance
            raise WrenError(f"{receiver.name} does not implement '{sig}'.")

        method = cls.lookup_method(sig)
        if not method:
            raise WrenError(f"{cls.name} does not implement '{sig}'.")
        return self.invoke_method(method, cls, receiver, args)

    def call_method_class(self, cls, receiver, sig, args):
        method = cls.lookup_method(sig)
        if not method:
            raise WrenError(f"{cls.name} does not implement '{sig}'.")
        return self.invoke_method(method, cls, receiver, args)

    def invoke_method(self, method, cls, receiver, args):
        if callable(method):
            return method(self, receiver, *args)
        elif isinstance(method, MethodDeclStmt):
            prev_class = self.current_class
            prev_instance = self.current_instance
            prev_env = self.environment

            env = Environment(self.environment)
            for param_name, arg_val in zip(method.params, args):
                env.define(param_name, arg_val)

            try:
                self.current_class = cls
                self.current_instance = receiver
                self.environment = env
                self.execute_block(method.body.statements, env)
                if method.is_construct:
                    return receiver
                return None
            except WrenReturn as ret:
                if method.is_construct:
                    return receiver
                return ret.value
            finally:
                self.current_class = prev_class
                self.current_instance = prev_instance
                self.environment = prev_env

    def call_fn(self, fn, args):
        if not isinstance(fn, WrenFn):
            raise WrenError("Target is not a function.")
        if len(args) != fn.arity:
            raise WrenError(f"Function expects {fn.arity} arguments but got {len(args)}.")

        env = Environment(fn.closure_env)
        for param, arg in zip(fn.params, args):
            env.define(param, arg)

        prev_env = self.environment
        try:
            self.environment = env
            last_val = None
            for stmt in fn.body.statements:
                last_val = self.execute(stmt)
            return last_val
        except WrenReturn as ret:
            return ret.value
        finally:
            self.environment = prev_env

    def run_fiber(self, fiber, val, is_try=False):
        if fiber.state in (WrenFiber.DONE, WrenFiber.ERROR):
            if is_try:
                return fiber.error_val
            raise WrenError("Cannot call a finished fiber.")

        prev_fiber = self.current_fiber
        fiber.caller = prev_fiber
        self.current_fiber = fiber
        fiber.state = WrenFiber.RUNNING

        try:
            res = self.call_fn(fiber.fn, [val] if val is not None and fiber.fn.arity == 1 else [])
            fiber.state = WrenFiber.DONE
            fiber.result = res
            return res
        except WrenError as err:
            fiber.state = WrenFiber.ERROR
            fiber.error_val = err.message
            if is_try:
                return err.message
            raise err
        finally:
            self.current_fiber = prev_fiber

    def yield_fiber(self, val):
        if not self.current_fiber or self.current_fiber.state != WrenFiber.RUNNING:
            raise WrenError("No fiber to yield from.")
        self.current_fiber.state = WrenFiber.SUSPENDED
        raise WrenError("Fiber yield not supported")

    def abort_fiber(self, err):
        if self.current_fiber:
            self.current_fiber.state = WrenFiber.ERROR
            self.current_fiber.error_val = str(err)
        raise WrenError(str(err))

    def transfer_fiber(self, fiber, val, is_error=False):
        if fiber.state in (WrenFiber.DONE, WrenFiber.ERROR):
            raise WrenError("Cannot transfer to a finished fiber.")
        return self.run_fiber(fiber, val, is_try=is_error)


# ==============================================================================
# 8. CLI ENTRY POINT
# ==============================================================================

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--help":
        print("Usage: wren [file] [arguments...]")
        print("\nOptional arguments:")
        print("  --help     Show command line usage")
        print("  --version  Show version")
        sys.exit(0)

    if len(sys.argv) == 2 and sys.argv[1] == "--version":
        print(f"wren {WREN_VERSION}")
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: wren [file]")
        sys.exit(64)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        sys.stderr.write(f'Could not find file "{file_path}".\n')
        sys.exit(66)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        sys.stderr.write(f'Could not read file "{file_path}".\n')
        sys.exit(74)

    root_dir = os.path.dirname(os.path.abspath(file_path))

    lexer = Lexer(source, file_path)
    tokens = lexer.scan_tokens()

    for t in tokens:
        if t.type == TokenType.ERROR:
            sys.stderr.write(f"[{file_path} line {t.line}] Error: {t.text}\n")
            sys.exit(65)

    try:
        parser = Parser(tokens)
        statements = parser.parse()
    except ParseError as pe:
        token = pe.token
        sys.stderr.write(f"[{file_path} line {token.line}] {pe.message}\n")
        sys.exit(65)
    except Exception as e:
        sys.stderr.write(f"Compile Error: {e}\n")
        sys.exit(65)

    try:
        interpreter = Interpreter(root_dir=root_dir)
        register_builtin_modules(interpreter)
        interpreter.interpret(statements)
        sys.exit(0)
    except WrenError as we:
        sys.stderr.write(f"{we.message}\n")
        sys.exit(70 if not we.is_compile_error else 65)
    except Exception as e:
        sys.stderr.write(f"Runtime Error: {e}\n")
        sys.exit(70)

if __name__ == "__main__":
    main()
