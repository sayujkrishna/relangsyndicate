#!/usr/bin/env python3
"""
PicoC C Interpreter in 100% Pure Python (Single File Standalone Distribution)
"""

import sys
import os
import struct
import re
from enum import Enum, auto

# Fix stdout line endings on Windows to match standard C behavior
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(newline='\n')


# ==============================================================================
# TYPES SYSTEM
# ==============================================================================

class BaseType(Enum):
    TypeInt = auto()
    TypeUnsignedInt = auto()
    TypeChar = auto()
    TypeUnsignedChar = auto()
    TypeShort = auto()
    TypeUnsignedShort = auto()
    TypeLong = auto()
    TypeUnsignedLong = auto()
    TypeFP = auto()
    TypeVoid = auto()
    TypePointer = auto()
    TypeArray = auto()
    TypeStruct = auto()
    TypeUnion = auto()
    TypeEnum = auto()
    TypeFunction = auto()


class ValueType:
    def __init__(self, base, sizeof=4, align_bytes=4, from_type=None, array_size=0, identifier=None):
        self.base = base
        self.sizeof = sizeof
        self.align_bytes = align_bytes
        self.from_type = from_type
        self.array_size = array_size
        self.identifier = identifier
        self.members = {}  # name -> (ValueType, offset)
        self.is_union = False
        self.static_qualifier = False

    def __repr__(self):
        if self.base == BaseType.TypePointer:
            return f"Pointer({repr(self.from_type)})"
        elif self.base == BaseType.TypeArray:
            return f"Array({repr(self.from_type)}[{self.array_size}])"
        elif self.base in (BaseType.TypeStruct, BaseType.TypeUnion):
            name = self.identifier or 'anonymous'
            kind = 'union' if self.is_union else 'struct'
            return f"{kind} {name}"
        return f"{self.base.name}"


class TypeSystem:
    def __init__(self):
        self.type_int = ValueType(BaseType.TypeInt, 4, 4)
        self.type_uint = ValueType(BaseType.TypeUnsignedInt, 4, 4)
        self.type_char = ValueType(BaseType.TypeChar, 1, 1)
        self.type_uchar = ValueType(BaseType.TypeUnsignedChar, 1, 1)
        self.type_short = ValueType(BaseType.TypeShort, 2, 2)
        self.type_ushort = ValueType(BaseType.TypeUnsignedShort, 2, 2)
        self.type_long = ValueType(BaseType.TypeLong, 4, 4)
        self.type_ulong = ValueType(BaseType.TypeUnsignedLong, 4, 4)
        self.type_fp = ValueType(BaseType.TypeFP, 8, 8)
        self.type_void = ValueType(BaseType.TypeVoid, 0, 1)

        self.type_char_ptr = self.create_pointer_type(self.type_char)
        self.type_void_ptr = self.create_pointer_type(self.type_void)

    def create_pointer_type(self, target_type):
        return ValueType(BaseType.TypePointer, sizeof=8, align_bytes=8, from_type=target_type)

    def create_array_type(self, elem_type, size):
        sz = (elem_type.sizeof * size) if elem_type else size
        return ValueType(BaseType.TypeArray, sizeof=sz, align_bytes=elem_type.align_bytes if elem_type else 4, from_type=elem_type, array_size=size)


# ==============================================================================
# LEXER & TOKENIZER
# ==============================================================================

class LexToken(Enum):
    TokenIntType = auto()
    TokenCharType = auto()
    TokenFloatType = auto()
    TokenDoubleType = auto()
    TokenVoidType = auto()
    TokenShortType = auto()
    TokenLongType = auto()
    TokenSignedType = auto()
    TokenUnsignedType = auto()
    TokenStructType = auto()
    TokenUnionType = auto()
    TokenEnumType = auto()
    TokenTypedef = auto()

    TokenIf = auto()
    TokenElse = auto()
    TokenWhile = auto()
    TokenDo = auto()
    TokenFor = auto()
    TokenSwitch = auto()
    TokenCase = auto()
    TokenDefault = auto()
    TokenGoto = auto()
    TokenBreak = auto()
    TokenContinue = auto()
    TokenReturn = auto()
    TokenSizeof = auto()
    TokenStaticType = auto()
    TokenExternType = auto()

    TokenHashInclude = auto()
    TokenHashDefine = auto()
    TokenHashIf = auto()
    TokenHashIfdef = auto()
    TokenHashIfndef = auto()
    TokenHashElse = auto()
    TokenHashEndif = auto()

    TokenIdentifier = auto()
    TokenIntegerConstant = auto()
    TokenFPConstant = auto()
    TokenStringConstant = auto()
    TokenCharacterConstant = auto()

    TokenAssign = auto()
    TokenPlus = auto()
    TokenMinus = auto()
    TokenAsterisk = auto()
    TokenSlash = auto()
    TokenPercent = auto()

    TokenAddAssign = auto()
    TokenSubAssign = auto()
    TokenMulAssign = auto()
    TokenDivAssign = auto()
    TokenModAssign = auto()

    TokenIncrement = auto()
    TokenDecrement = auto()

    TokenEqual = auto()
    TokenNotEqual = auto()
    TokenLessThan = auto()
    TokenGreaterThan = auto()
    TokenLessEqual = auto()
    TokenGreaterEqual = auto()

    TokenLogicalAnd = auto()
    TokenLogicalOr = auto()
    TokenLogicalNot = auto()

    TokenAmpersand = auto()
    TokenBitwiseOr = auto()
    TokenBitwiseXor = auto()
    TokenBitwiseNot = auto()
    TokenShiftLeft = auto()
    TokenShiftRight = auto()

    TokenShiftLeftAssign = auto()
    TokenShiftRightAssign = auto()
    TokenBitwiseAndAssign = auto()
    TokenBitwiseOrAssign = auto()
    TokenBitwiseXorAssign = auto()

    TokenQuestion = auto()
    TokenColon = auto()
    TokenDot = auto()
    TokenArrow = auto()
    TokenComma = auto()
    TokenSemicolon = auto()
    TokenEllipsis = auto()

    TokenOpenBracket = auto()
    TokenCloseBracket = auto()
    TokenLeftBrace = auto()
    TokenRightBrace = auto()
    TokenLeftSquareBracket = auto()
    TokenRightSquareBracket = auto()

    TokenEOF = auto()


KEYWORDS = {
    "int": LexToken.TokenIntType,
    "char": LexToken.TokenCharType,
    "float": LexToken.TokenFloatType,
    "double": LexToken.TokenDoubleType,
    "void": LexToken.TokenVoidType,
    "short": LexToken.TokenShortType,
    "long": LexToken.TokenLongType,
    "signed": LexToken.TokenSignedType,
    "unsigned": LexToken.TokenUnsignedType,
    "struct": LexToken.TokenStructType,
    "union": LexToken.TokenUnionType,
    "enum": LexToken.TokenEnumType,
    "typedef": LexToken.TokenTypedef,
    "if": LexToken.TokenIf,
    "else": LexToken.TokenElse,
    "while": LexToken.TokenWhile,
    "do": LexToken.TokenDo,
    "for": LexToken.TokenFor,
    "switch": LexToken.TokenSwitch,
    "case": LexToken.TokenCase,
    "default": LexToken.TokenDefault,
    "goto": LexToken.TokenGoto,
    "break": LexToken.TokenBreak,
    "continue": LexToken.TokenContinue,
    "return": LexToken.TokenReturn,
    "sizeof": LexToken.TokenSizeof,
    "static": LexToken.TokenStaticType,
    "extern": LexToken.TokenExternType,
}


class Token:
    def __init__(self, token_type, value=None, line=1, column=1):
        self.type = token_type
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type.name}, {repr(self.value)})"


def lex_analyse(source_code, file_name="<input>"):
    tokens = []
    pos = 0
    length = len(source_code)
    line = 1
    col = 1

    while pos < length:
        ch = source_code[pos]

        if ch in ' \t\r':
            pos += 1
            col += 1
            continue

        if ch == '\n':
            pos += 1
            line += 1
            col = 1
            continue

        if source_code.startswith('/*', pos):
            pos += 2
            col += 2
            while pos < length and not source_code.startswith('*/', pos):
                if source_code[pos] == '\n':
                    line += 1
                    col = 1
                else:
                    col += 1
                pos += 1
            if pos < length:
                pos += 2
                col += 2
            continue

        if source_code.startswith('//', pos):
            pos += 2
            while pos < length and source_code[pos] != '\n':
                pos += 1
            continue

        if ch == '#' and (pos == 0 or source_code[pos - 1] == '\n' or source_code[:pos].strip().endswith('\n')):
            start_pos = pos
            while pos < length and source_code[pos] not in (' ', '\t', '\n', '<', '"'):
                pos += 1
            directive = source_code[start_pos:pos].strip()
            if directive == '#include':
                tokens.append(Token(LexToken.TokenHashInclude, '#include', line, col))
            elif directive == '#define':
                tokens.append(Token(LexToken.TokenHashDefine, '#define', line, col))
            elif directive == '#if':
                tokens.append(Token(LexToken.TokenHashIf, '#if', line, col))
            elif directive == '#ifdef':
                tokens.append(Token(LexToken.TokenHashIfdef, '#ifdef', line, col))
            elif directive == '#ifndef':
                tokens.append(Token(LexToken.TokenHashIfndef, '#ifndef', line, col))
            elif directive == '#else':
                tokens.append(Token(LexToken.TokenHashElse, '#else', line, col))
            elif directive == '#endif':
                tokens.append(Token(LexToken.TokenHashEndif, '#endif', line, col))
            else:
                tokens.append(Token(LexToken.TokenHashDefine, directive, line, col))
            col += (pos - start_pos)
            continue

        if ch == '"':
            pos += 1
            col += 1
            str_val = []
            while pos < length and source_code[pos] != '"':
                if source_code[pos] == '\\' and pos + 1 < length:
                    pos += 1
                    col += 1
                    esc = source_code[pos]
                    if esc == 'n': str_val.append('\n')
                    elif esc == 't': str_val.append('\t')
                    elif esc == 'r': str_val.append('\r')
                    elif esc == '0': str_val.append('\0')
                    elif esc == '\\': str_val.append('\\')
                    elif esc == '"': str_val.append('"')
                    else: str_val.append(esc)
                else:
                    str_val.append(source_code[pos])
                pos += 1
                col += 1
            if pos < length and source_code[pos] == '"':
                pos += 1
                col += 1
            tokens.append(Token(LexToken.TokenStringConstant, "".join(str_val), line, col))
            continue

        if ch == "'":
            pos += 1
            col += 1
            char_val = 0
            if pos < length and source_code[pos] == '\\':
                pos += 1
                col += 1
                esc = source_code[pos]
                if esc == 'n': char_val = ord('\n')
                elif esc == 't': char_val = ord('\t')
                elif esc == '0': char_val = 0
                elif esc == '\\': char_val = ord('\\')
                elif esc == "'": char_val = ord("'")
                else: char_val = ord(esc)
                pos += 1
                col += 1
            elif pos < length:
                char_val = ord(source_code[pos])
                pos += 1
                col += 1
            if pos < length and source_code[pos] == "'":
                pos += 1
                col += 1
            tokens.append(Token(LexToken.TokenCharacterConstant, char_val, line, col))
            continue

        if ch.isdigit() or (ch == '.' and pos + 1 < length and source_code[pos + 1].isdigit()):
            start_pos = pos
            is_float = False
            if source_code.startswith(('0x', '0X'), pos):
                pos += 2
                while pos < length and source_code[pos] in '0123456789abcdefABCDEF':
                    pos += 1
                val = int(source_code[start_pos:pos], 16)
                tokens.append(Token(LexToken.TokenIntegerConstant, val, line, col))
            else:
                while pos < length and (source_code[pos].isdigit() or source_code[pos] in '.eE'):
                    if source_code[pos] in '.eE':
                        is_float = True
                    pos += 1
                if pos < length and source_code[pos] in 'fFlL':
                    pos += 1
                val_str = source_code[start_pos:pos].rstrip('fFlL')
                val = float(val_str) if is_float else int(val_str)
                tok_t = LexToken.TokenFPConstant if is_float else LexToken.TokenIntegerConstant
                tokens.append(Token(tok_t, val, line, col))
            col += (pos - start_pos)
            continue

        if ch.isalpha() or ch == '_':
            start_pos = pos
            while pos < length and (source_code[pos].isalnum() or source_code[pos] == '_'):
                pos += 1
            ident = source_code[start_pos:pos]
            tok_t = KEYWORDS.get(ident, LexToken.TokenIdentifier)
            tokens.append(Token(tok_t, ident, line, col))
            col += (pos - start_pos)
            continue

        two_char = source_code[pos:pos+2]
        three_char = source_code[pos:pos+3]

        if three_char == '...':
            tokens.append(Token(LexToken.TokenEllipsis, '...', line, col))
            pos += 3; col += 3; continue
        elif two_char == '++':
            tokens.append(Token(LexToken.TokenIncrement, '++', line, col))
            pos += 2; col += 2; continue
        elif two_char == '--':
            tokens.append(Token(LexToken.TokenDecrement, '--', line, col))
            pos += 2; col += 2; continue
        elif two_char == '==':
            tokens.append(Token(LexToken.TokenEqual, '==', line, col))
            pos += 2; col += 2; continue
        elif two_char == '!=':
            tokens.append(Token(LexToken.TokenNotEqual, '!=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '<=':
            tokens.append(Token(LexToken.TokenLessEqual, '<=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '>=':
            tokens.append(Token(LexToken.TokenGreaterEqual, '>=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '&&':
            tokens.append(Token(LexToken.TokenLogicalAnd, '&&', line, col))
            pos += 2; col += 2; continue
        elif two_char == '||':
            tokens.append(Token(LexToken.TokenLogicalOr, '||', line, col))
            pos += 2; col += 2; continue
        elif two_char == '->':
            tokens.append(Token(LexToken.TokenArrow, '->', line, col))
            pos += 2; col += 2; continue
        elif two_char == '+=':
            tokens.append(Token(LexToken.TokenAddAssign, '+=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '-=':
            tokens.append(Token(LexToken.TokenSubAssign, '-=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '*=':
            tokens.append(Token(LexToken.TokenMulAssign, '*=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '/=':
            tokens.append(Token(LexToken.TokenDivAssign, '/=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '%=':
            tokens.append(Token(LexToken.TokenModAssign, '%=', line, col))
            pos += 2; col += 2; continue
        elif two_char == '<<':
            tokens.append(Token(LexToken.TokenShiftLeft, '<<', line, col))
            pos += 2; col += 2; continue
        elif two_char == '>>':
            tokens.append(Token(LexToken.TokenShiftRight, '>>', line, col))
            pos += 2; col += 2; continue

        single_ops = {
            '=': LexToken.TokenAssign,
            '+': LexToken.TokenPlus,
            '-': LexToken.TokenMinus,
            '*': LexToken.TokenAsterisk,
            '/': LexToken.TokenSlash,
            '%': LexToken.TokenPercent,
            '<': LexToken.TokenLessThan,
            '>': LexToken.TokenGreaterThan,
            '!': LexToken.TokenLogicalNot,
            '&': LexToken.TokenAmpersand,
            '|': LexToken.TokenBitwiseOr,
            '^': LexToken.TokenBitwiseXor,
            '~': LexToken.TokenBitwiseNot,
            '?': LexToken.TokenQuestion,
            ':': LexToken.TokenColon,
            '.': LexToken.TokenDot,
            ',': LexToken.TokenComma,
            ';': LexToken.TokenSemicolon,
            '(': LexToken.TokenOpenBracket,
            ')': LexToken.TokenCloseBracket,
            '{': LexToken.TokenLeftBrace,
            '}': LexToken.TokenRightBrace,
            '[': LexToken.TokenLeftSquareBracket,
            ']': LexToken.TokenRightSquareBracket,
        }

        if ch in single_ops:
            tokens.append(Token(single_ops[ch], ch, line, col))
            pos += 1
            col += 1
            continue

        pos += 1
        col += 1

    tokens.append(Token(LexToken.TokenEOF, None, line, col))
    return tokens


# ==============================================================================
# SYMBOL TABLE & SCOPE
# ==============================================================================

class Table:
    def __init__(self, parent=None):
        self.parent = parent
        self.entries = {}

    def get(self, name):
        if name in self.entries:
            return self.entries[name]
        if self.parent:
            return self.parent.get(name)
        return None

    def define(self, name, value):
        self.entries[name] = value


# ==============================================================================
# VALUES & POINTERS
# ==============================================================================

class Pointer:
    def __init__(self, base_obj, offset=0, target_type=None):
        self.base_obj = base_obj
        self.offset = offset
        self.target_type = target_type

    def __add__(self, delta):
        if isinstance(self.base_obj, list):
            step = 1
        else:
            elem_t = self.target_type.from_type if (self.target_type and self.target_type.from_type) else None
            if elem_t and elem_t.base == BaseType.TypeArray:
                elem_t = elem_t.from_type
            step = elem_t.sizeof if (elem_t and elem_t.sizeof > 0) else 1
        return Pointer(self.base_obj, self.offset + delta * step, self.target_type)

    def __sub__(self, other):
        if isinstance(self.base_obj, list):
            step = 1
        else:
            elem_t = self.target_type.from_type if (self.target_type and self.target_type.from_type) else None
            if elem_t and elem_t.base == BaseType.TypeArray:
                elem_t = elem_t.from_type
            step = elem_t.sizeof if (elem_t and elem_t.sizeof > 0) else 1

        if isinstance(other, Pointer):
            return (self.offset - other.offset) // (step if step > 0 else 1)
        elif isinstance(other, int):
            return Pointer(self.base_obj, self.offset - other * step, self.target_type)
        return 0

    def deref(self):
        if isinstance(self.base_obj, Value):
            if isinstance(self.base_obj.val, list):
                if 0 <= self.offset < len(self.base_obj.val):
                    return self.base_obj.val[self.offset]
                return 0
            elif isinstance(self.base_obj.val, bytearray):
                return self.read_bytearray(self.base_obj.val, self.offset)
            return self.base_obj.val
        elif isinstance(self.base_obj, list):
            if 0 <= self.offset < len(self.base_obj):
                return self.base_obj[self.offset]
            return 0
        elif isinstance(self.base_obj, bytearray):
            return self.read_bytearray(self.base_obj, self.offset)
        elif isinstance(self.base_obj, str):
            if 0 <= self.offset < len(self.base_obj):
                return ord(self.base_obj[self.offset])
            return 0
        elif isinstance(self.base_obj, Pointer):
            return self.base_obj.deref()
        return 0

    def read_bytearray(self, buf, off):
        elem_t = self.target_type.from_type if (self.target_type and self.target_type.from_type) else None
        if elem_t and elem_t.base == BaseType.TypeArray:
            elem_t = elem_t.from_type
        sz = elem_t.sizeof if elem_t else 1
        if off + sz <= len(buf):
            if sz == 1:
                return buf[off]
            elif sz == 2:
                return int.from_bytes(buf[off:off+2], 'little', signed=True)
            elif sz == 4:
                if elem_t and elem_t.base == BaseType.TypeFP:
                    return struct.unpack('<f', buf[off:off+4])[0]
                return int.from_bytes(buf[off:off+4], 'little', signed=True)
            elif sz == 8:
                if elem_t and elem_t.base == BaseType.TypeFP:
                    return struct.unpack('<d', buf[off:off+8])[0]
                return int.from_bytes(buf[off:off+8], 'little', signed=True)
        elif 0 <= off < len(buf):
            return buf[off]
        return 0

    def set_deref(self, val):
        if isinstance(val, Value):
            val = val.val
        if isinstance(self.base_obj, Value):
            if isinstance(self.base_obj.val, list):
                if 0 <= self.offset < len(self.base_obj.val):
                    self.base_obj.val[self.offset] = val
            elif isinstance(self.base_obj.val, bytearray):
                self.write_bytearray(self.base_obj.val, self.offset, val)
            else:
                self.base_obj.set_val(val)
        elif isinstance(self.base_obj, list):
            if 0 <= self.offset < len(self.base_obj):
                self.base_obj[self.offset] = val
        elif isinstance(self.base_obj, bytearray):
            self.write_bytearray(self.base_obj, self.offset, val)
        elif isinstance(self.base_obj, Pointer):
            self.base_obj.set_deref(val)

    def write_bytearray(self, buf, off, val):
        elem_t = self.target_type.from_type if (self.target_type and self.target_type.from_type) else None
        if elem_t and elem_t.base == BaseType.TypeArray:
            elem_t = elem_t.from_type
        sz = elem_t.sizeof if elem_t else 1
        if off + sz <= len(buf):
            if sz == 1:
                buf[off] = int(val) & 0xFF
            elif sz == 2:
                buf[off:off+2] = int(val).to_bytes(2, 'little', signed=True)
            elif sz == 4:
                if elem_t and elem_t.base == BaseType.TypeFP:
                    buf[off:off+4] = struct.pack('<f', float(val))
                else:
                    buf[off:off+4] = int(val).to_bytes(4, 'little', signed=True)
            elif sz == 8:
                if elem_t and elem_t.base == BaseType.TypeFP:
                    buf[off:off+8] = struct.pack('<d', float(val))
                else:
                    buf[off:off+8] = int(val).to_bytes(8, 'little', signed=True)
        elif 0 <= off < len(buf):
            buf[off] = int(val) & 0xFF

    def __eq__(self, other):
        if isinstance(other, Pointer):
            return self.base_obj is other.base_obj and self.offset == other.offset
        elif other == 0 or other is None:
            return self.base_obj is None or (self.offset == 0 and self.base_obj is None)
        return False

    def __bool__(self):
        return self.base_obj is not None

    def __repr__(self):
        return f"Pointer(offset={self.offset})"


class Value:
    def __init__(self, typ, val=None, is_lvalue=False, lvalue_from=None, scope_id=0):
        self.typ = typ
        self.val = None
        self.is_lvalue = is_lvalue
        self.lvalue_from = lvalue_from
        self.scope_id = scope_id
        if val is not None:
            self.set_val(val)

    def get_int(self):
        if isinstance(self.val, Pointer):
            return self.val.offset
        if self.val is None:
            return 0
        if isinstance(self.val, (int, float)):
            return int(self.val)
        if isinstance(self.val, str):
            return ord(self.val[0]) if self.val else 0
        if isinstance(self.val, Value):
            return self.val.get_int()
        return 0

    def get_float(self):
        if self.val is None:
            return 0.0
        if isinstance(self.val, (int, float)):
            return float(self.val)
        return 0.0

    def set_val(self, new_val):
        if isinstance(new_val, Value):
            new_val = new_val.val
        if self.typ.base == BaseType.TypeChar:
            if isinstance(new_val, (int, float)):
                v = int(new_val) & 0xFF
                self.val = v - 256 if v >= 128 else v
            else:
                self.val = new_val
        elif self.typ.base == BaseType.TypeUnsignedChar:
            self.val = int(new_val) & 0xFF if isinstance(new_val, (int, float)) else new_val
        elif self.typ.base in (BaseType.TypeInt, BaseType.TypeShort, BaseType.TypeLong):
            self.val = int(new_val) if isinstance(new_val, (int, float)) else new_val
        elif self.typ.base in (BaseType.TypeUnsignedInt, BaseType.TypeUnsignedShort, BaseType.TypeUnsignedLong):
            self.val = int(new_val) & 0xFFFFFFFF if isinstance(new_val, (int, float)) else new_val
        elif self.typ.base == BaseType.TypeFP:
            self.val = float(new_val) if isinstance(new_val, (int, float)) else new_val
        else:
            self.val = new_val

    def __repr__(self):
        return f"Value({self.typ}, {repr(self.val)})"


# ==============================================================================
# C STANDARD LIBRARY EMULATION
# ==============================================================================

class CStdLibrary:
    def __init__(self, parser_state):
        self.ps = parser_state

    def register_all(self):
        return {
            "printf": self.c_printf,
            "sprintf": self.c_sprintf,
            "snprintf": self.c_snprintf,
            "malloc": self.c_malloc,
            "calloc": self.c_calloc,
            "realloc": self.c_realloc,
            "free": self.c_free,
            "strcpy": self.c_strcpy,
            "strlen": self.c_strlen,
            "strcat": self.c_strcat,
            "strcmp": self.c_strcmp,
            "memset": self.c_memset,
            "memcpy": self.c_memcpy,
            "abs": self.c_abs,
        }

    def c_printf(self, args):
        if not args:
            return 0
        fmt_arg = args[0]
        fmt_str = ""
        if isinstance(fmt_arg.val, Pointer):
            ptr = fmt_arg.val
            if isinstance(ptr.base_obj, str):
                fmt_str = ptr.base_obj[ptr.offset:]
            elif isinstance(ptr.base_obj, list):
                chars = []
                for idx in range(ptr.offset, len(ptr.base_obj)):
                    ch = ptr.base_obj[idx]
                    if ch == 0:
                        break
                    chars.append(chr(ch) if isinstance(ch, int) else str(ch))
                fmt_str = "".join(chars)
            elif isinstance(ptr.base_obj, bytearray):
                buf = ptr.base_obj[ptr.offset:]
                null_pos = buf.find(b'\0')
                if null_pos != -1:
                    buf = buf[:null_pos]
                fmt_str = buf.decode('utf-8', errors='ignore')
        elif isinstance(fmt_arg.val, str):
            fmt_str = fmt_arg.val

        specifiers = re.findall(r'%[-+ 0]*\d*(?:\.\d+)?[diufFeEgGxXosc%]', fmt_str)
        var_args = args[1:]
        out_parts = []
        spec_idx = 0

        pos = 0
        for match in re.finditer(r'%[-+ 0]*\d*(?:\.\d+)?[diufFeEgGxXosc%]', fmt_str):
            out_parts.append(fmt_str[pos:match.start()])
            spec = match.group(0)
            pos = match.end()

            if spec == "%%":
                out_parts.append("%")
                continue

            if spec_idx < len(var_args):
                arg = var_args[spec_idx]
                spec_idx += 1
                val = arg.val if isinstance(arg, Value) else arg

                if spec[-1] in 'di':
                    v_int = arg.get_int() if isinstance(arg, Value) else int(val)
                    fmt_py = spec.replace('i', 'd')
                    out_parts.append(fmt_py % v_int)
                elif spec[-1] in 'fFeEgG':
                    v_flt = arg.get_float() if isinstance(arg, Value) else float(val)
                    out_parts.append(spec % v_flt)
                elif spec[-1] == 's':
                    s_str = ""
                    if isinstance(val, Pointer):
                        if isinstance(val.base_obj, str):
                            s_str = val.base_obj[val.offset:]
                        elif isinstance(val.base_obj, list):
                            chars = []
                            for idx in range(val.offset, len(val.base_obj)):
                                ch = val.base_obj[idx]
                                if ch == 0:
                                    break
                                chars.append(chr(ch) if isinstance(ch, int) else str(ch))
                            s_str = "".join(chars)
                        elif isinstance(val.base_obj, bytearray):
                            buf = val.base_obj[val.offset:]
                            null_pos = buf.find(b'\0')
                            if null_pos != -1:
                                buf = buf[:null_pos]
                            s_str = buf.decode('utf-8', errors='ignore')
                    elif isinstance(val, str):
                        s_str = val
                    fmt_py = spec
                    out_parts.append(fmt_py % s_str)
                elif spec[-1] == 'c':
                    v_char = chr(arg.get_int() if isinstance(arg, Value) else int(val))
                    out_parts.append(v_char)
                else:
                    v_int = arg.get_int() if isinstance(arg, Value) else int(val)
                    out_parts.append(spec % v_int)
            else:
                out_parts.append(spec)

        out_parts.append(fmt_str[pos:])
        res_str = "".join(out_parts)
        sys.stdout.write(res_str)
        sys.stdout.flush()
        return len(res_str)

    def c_sprintf(self, args):
        if len(args) < 2:
            return 0
        buf_ptr = args[0].val
        fmt_arg = args[1]
        fmt_str = ""
        if isinstance(fmt_arg.val, Pointer):
            fmt_str = fmt_arg.val.base_obj[fmt_arg.val.offset:] if isinstance(fmt_arg.val.base_obj, str) else ""
        elif isinstance(fmt_arg.val, str):
            fmt_str = fmt_arg.val

        var_args = args[2:]
        spec_idx = 0
        out_parts = []
        pos = 0
        for match in re.finditer(r'%[-+ 0]*\d*(?:\.\d+)?[diufFeEgGxXosc%]', fmt_str):
            out_parts.append(fmt_str[pos:match.start()])
            spec = match.group(0)
            pos = match.end()

            if spec == "%%":
                out_parts.append("%")
                continue

            if spec_idx < len(var_args):
                arg = var_args[spec_idx]
                spec_idx += 1
                val = arg.val if isinstance(arg, Value) else arg

                if spec[-1] in 'di':
                    v_int = arg.get_int() if isinstance(arg, Value) else int(val)
                    fmt_py = spec.replace('i', 'd')
                    out_parts.append(fmt_py % v_int)
                elif spec[-1] in 'fFeEgG':
                    v_flt = arg.get_float() if isinstance(arg, Value) else float(val)
                    out_parts.append(spec % v_flt)
                elif spec[-1] == 's':
                    s_str = val.base_obj[val.offset:] if isinstance(val, Pointer) and isinstance(val.base_obj, str) else str(val)
                    out_parts.append(spec % s_str)
                else:
                    v_int = arg.get_int() if isinstance(arg, Value) else int(val)
                    out_parts.append(spec % v_int)
            else:
                out_parts.append(spec)

        out_parts.append(fmt_str[pos:])
        res_str = "".join(out_parts)

        if isinstance(buf_ptr, Pointer):
            if isinstance(buf_ptr.base_obj, bytearray):
                b_res = res_str.encode('utf-8') + b'\0'
                off = buf_ptr.offset
                buf_ptr.base_obj[off:off+len(b_res)] = b_res
            elif isinstance(buf_ptr.base_obj, list):
                for idx, c in enumerate(res_str):
                    buf_ptr.base_obj[buf_ptr.offset + idx] = ord(c)
                buf_ptr.base_obj[buf_ptr.offset + len(res_str)] = 0
        return len(res_str)

    def c_snprintf(self, args):
        if len(args) < 3:
            return 0
        return self.c_sprintf([args[0], args[2]] + args[3:])

    def c_malloc(self, args):
        sz = args[0].get_int() if args else 0
        buf = bytearray(sz if sz > 0 else 8)
        ptr = Pointer(buf, 0, self.ps.types.type_void_ptr)
        return Value(self.ps.types.type_void_ptr, ptr)

    def c_calloc(self, args):
        num = args[0].get_int() if len(args) > 0 else 0
        sz = args[1].get_int() if len(args) > 1 else 0
        total = num * sz
        buf = bytearray(total if total > 0 else 8)
        ptr = Pointer(buf, 0, self.ps.types.type_void_ptr)
        return Value(self.ps.types.type_void_ptr, ptr)

    def c_realloc(self, args):
        ptr = args[0].val if len(args) > 0 else None
        new_sz = args[1].get_int() if len(args) > 1 else 0
        if ptr is None or ptr == 0:
            return self.c_malloc([args[1]])
        if isinstance(ptr, Pointer) and isinstance(ptr.base_obj, bytearray):
            if new_sz > len(ptr.base_obj):
                ptr.base_obj.extend(b'\0' * (new_sz - len(ptr.base_obj)))
            return args[0]
        return self.c_malloc([args[1]])

    def c_free(self, args):
        return 0

    def c_strlen(self, args):
        if not args:
            return 0
        ptr = args[0].val
        if isinstance(ptr, Pointer):
            if isinstance(ptr.base_obj, str):
                return len(ptr.base_obj) - ptr.offset
            elif isinstance(ptr.base_obj, list):
                length = 0
                for idx in range(ptr.offset, len(ptr.base_obj)):
                    if ptr.base_obj[idx] == 0:
                        break
                    length += 1
                return length
            elif isinstance(ptr.base_obj, bytearray):
                buf = ptr.base_obj[ptr.offset:]
                null_pos = buf.find(b'\0')
                return null_pos if null_pos != -1 else len(buf)
        return 0

    def c_strcpy(self, args):
        if len(args) < 2:
            return 0
        dest_ptr = args[0].val
        src_ptr = args[1].val
        src_str = ""
        if isinstance(src_ptr, Pointer):
            if isinstance(src_ptr.base_obj, str):
                src_str = src_ptr.base_obj[src_ptr.offset:]
            elif isinstance(src_ptr.base_obj, list):
                chars = []
                for idx in range(src_ptr.offset, len(src_ptr.base_obj)):
                    ch = src_ptr.base_obj[idx]
                    if ch == 0: break
                    chars.append(chr(ch) if isinstance(ch, int) else str(ch))
                src_str = "".join(chars)
            elif isinstance(src_ptr.base_obj, bytearray):
                buf = src_ptr.base_obj[src_ptr.offset:]
                null_pos = buf.find(b'\0')
                if null_pos != -1: buf = buf[:null_pos]
                src_str = buf.decode('utf-8', errors='ignore')

        if isinstance(dest_ptr, Pointer):
            if isinstance(dest_ptr.base_obj, list):
                for idx, c in enumerate(src_str):
                    dest_ptr.base_obj[dest_ptr.offset + idx] = ord(c)
                dest_ptr.base_obj[dest_ptr.offset + len(src_str)] = 0
            elif isinstance(dest_ptr.base_obj, bytearray):
                b_res = src_str.encode('utf-8') + b'\0'
                off = dest_ptr.offset
                dest_ptr.base_obj[off:off+len(b_res)] = b_res
        return args[0]

    def c_strcat(self, args):
        if len(args) < 2:
            return 0
        dest_ptr = args[0].val
        src_ptr = args[1].val
        curr_len = self.c_strlen([args[0]])
        if isinstance(dest_ptr, Pointer):
            new_dest = Pointer(dest_ptr.base_obj, dest_ptr.offset + curr_len, dest_ptr.target_type)
            self.c_strcpy([Value(dest_ptr.target_type, new_dest), args[1]])
        return args[0]

    def c_strcmp(self, args):
        if len(args) < 2:
            return 0
        s1 = self.get_str(args[0].val)
        s2 = self.get_str(args[1].val)
        if s1 < s2: return -1
        elif s1 > s2: return 1
        return 0

    def get_str(self, ptr):
        if isinstance(ptr, Pointer):
            if isinstance(ptr.base_obj, str): return ptr.base_obj[ptr.offset:]
            elif isinstance(ptr.base_obj, list):
                res = []
                for i in range(ptr.offset, len(ptr.base_obj)):
                    if ptr.base_obj[i] == 0: break
                    res.append(chr(ptr.base_obj[i]))
                return "".join(res)
            elif isinstance(ptr.base_obj, bytearray):
                buf = ptr.base_obj[ptr.offset:]
                null_pos = buf.find(b'\0')
                if null_pos != -1: buf = buf[:null_pos]
                return buf.decode('utf-8', errors='ignore')
        return ""

    def c_memset(self, args):
        if len(args) < 3: return 0
        ptr = args[0].val
        val = args[1].get_int()
        num = args[2].get_int()
        if isinstance(ptr, Pointer):
            if isinstance(ptr.base_obj, bytearray):
                off = ptr.offset
                for i in range(num):
                    if off + i < len(ptr.base_obj):
                        ptr.base_obj[off + i] = val & 0xFF
            elif isinstance(ptr.base_obj, list):
                off = ptr.offset
                for i in range(num):
                    if off + i < len(ptr.base_obj):
                        ptr.base_obj[off + i] = val
        return args[0]

    def c_memcpy(self, args):
        if len(args) < 3: return 0
        dest = args[0].val
        src = args[1].val
        num = args[2].get_int()
        if isinstance(dest, Pointer) and isinstance(src, Pointer):
            if isinstance(dest.base_obj, bytearray) and isinstance(src.base_obj, bytearray):
                d_off = dest.offset
                s_off = src.offset
                dest.base_obj[d_off:d_off+num] = src.base_obj[s_off:s_off+num]
            elif isinstance(dest.base_obj, list) and isinstance(src.base_obj, list):
                d_off = dest.offset
                s_off = src.offset
                for i in range(num):
                    if s_off + i < len(src.base_obj) and d_off + i < len(dest.base_obj):
                        dest.base_obj[d_off + i] = src.base_obj[s_off + i]
        return args[0]

    def c_abs(self, args):
        if not args: return 0
        return abs(args[0].get_int())


# ==============================================================================
# EXPRESSION PARSER
# ==============================================================================

class ExpressionParser:
    def __init__(self, parser_state):
        self.ps = parser_state

    def parse_expression(self):
        return self.parse_assignment()

    def parse_assignment(self):
        left = self.parse_conditional()
        tok = self.ps.peek_token()
        if tok.type in (
            LexToken.TokenAssign, LexToken.TokenAddAssign, LexToken.TokenSubAssign,
            LexToken.TokenMulAssign, LexToken.TokenDivAssign, LexToken.TokenModAssign,
            LexToken.TokenShiftLeftAssign, LexToken.TokenShiftRightAssign,
            LexToken.TokenBitwiseAndAssign, LexToken.TokenBitwiseOrAssign, LexToken.TokenBitwiseXorAssign
        ):
            op = self.ps.match_token()
            right = self.parse_assignment()
            return self.eval_assign(left, op, right)
        return left

    def eval_assign(self, left, op, right):
        right_val = right.val if isinstance(right, Value) else right
        target_val = right_val
        if op.type != LexToken.TokenAssign:
            curr_val = left.val if isinstance(left, Value) else left
            if isinstance(curr_val, Pointer):
                curr = curr_val.deref()
            else:
                curr = curr_val
            r_num = right.get_int() if isinstance(right, Value) else int(right_val)

            if op.type == LexToken.TokenAddAssign: target_val = curr + r_num
            elif op.type == LexToken.TokenSubAssign: target_val = curr - r_num
            elif op.type == LexToken.TokenMulAssign: target_val = curr * r_num
            elif op.type == LexToken.TokenDivAssign: target_val = curr // r_num if r_num != 0 else 0
            elif op.type == LexToken.TokenModAssign: target_val = curr % r_num if r_num != 0 else 0
            elif op.type == LexToken.TokenShiftLeftAssign: target_val = curr << r_num
            elif op.type == LexToken.TokenShiftRightAssign: target_val = curr >> r_num
            elif op.type == LexToken.TokenBitwiseAndAssign: target_val = curr & r_num
            elif op.type == LexToken.TokenBitwiseOrAssign: target_val = curr | r_num
            elif op.type == LexToken.TokenBitwiseXorAssign: target_val = curr ^ r_num

        if isinstance(left, Value):
            if hasattr(left, 'lvalue_ptr') and left.lvalue_ptr:
                left.lvalue_ptr.set_deref(target_val)
                left.set_val(target_val)
            else:
                left.set_val(target_val)
            return left
        return Value(self.ps.types.type_int, target_val)

    def parse_conditional(self):
        cond = self.parse_logical_or()
        if self.ps.peek_token().type == LexToken.TokenQuestion:
            self.ps.match_token()
            then_expr = self.parse_expression()
            self.ps.expect(LexToken.TokenColon)
            else_expr = self.parse_conditional()
            c_val = cond.get_int() if isinstance(cond, Value) else bool(cond)
            return then_expr if c_val else else_expr
        return cond

    def parse_logical_or(self):
        left = self.parse_logical_and()
        while self.ps.peek_token().type == LexToken.TokenLogicalOr:
            self.ps.match_token()
            right = self.parse_logical_and()
            l_val = left.get_int() if isinstance(left, Value) else bool(left)
            r_val = right.get_int() if isinstance(right, Value) else bool(right)
            left = Value(self.ps.types.type_int, 1 if (l_val or r_val) else 0)
        return left

    def parse_logical_and(self):
        left = self.parse_bitwise_or()
        while self.ps.peek_token().type == LexToken.TokenLogicalAnd:
            self.ps.match_token()
            right = self.parse_bitwise_or()
            l_val = left.get_int() if isinstance(left, Value) else bool(left)
            r_val = right.get_int() if isinstance(right, Value) else bool(right)
            left = Value(self.ps.types.type_int, 1 if (l_val and r_val) else 0)
        return left

    def parse_bitwise_or(self):
        left = self.parse_bitwise_xor()
        while self.ps.peek_token().type == LexToken.TokenBitwiseOr:
            self.ps.match_token()
            right = self.parse_bitwise_xor()
            l_val = left.get_int() if isinstance(left, Value) else int(left)
            r_val = right.get_int() if isinstance(right, Value) else int(right)
            left = Value(self.ps.types.type_int, l_val | r_val)
        return left

    def parse_bitwise_xor(self):
        left = self.parse_bitwise_and()
        while self.ps.peek_token().type == LexToken.TokenBitwiseXor:
            self.ps.match_token()
            right = self.parse_bitwise_and()
            l_val = left.get_int() if isinstance(left, Value) else int(left)
            r_val = right.get_int() if isinstance(right, Value) else int(right)
            left = Value(self.ps.types.type_int, l_val ^ r_val)
        return left

    def parse_bitwise_and(self):
        left = self.parse_equality()
        while self.ps.peek_token().type == LexToken.TokenAmpersand:
            self.ps.match_token()
            right = self.parse_equality()
            l_val = left.get_int() if isinstance(left, Value) else int(left)
            r_val = right.get_int() if isinstance(right, Value) else int(right)
            left = Value(self.ps.types.type_int, l_val & r_val)
        return left

    def parse_equality(self):
        left = self.parse_relational()
        while self.ps.peek_token().type in (LexToken.TokenEqual, LexToken.TokenNotEqual):
            op = self.ps.match_token()
            right = self.parse_relational()
            l_val = left.val if isinstance(left, Value) else left
            r_val = right.val if isinstance(right, Value) else right
            if op.type == LexToken.TokenEqual:
                res = 1 if l_val == r_val else 0
            else:
                res = 1 if l_val != r_val else 0
            left = Value(self.ps.types.type_int, res)
        return left

    def parse_relational(self):
        left = self.parse_shift()
        while self.ps.peek_token().type in (LexToken.TokenLessThan, LexToken.TokenGreaterThan, LexToken.TokenLessEqual, LexToken.TokenGreaterEqual):
            op = self.ps.match_token()
            right = self.parse_shift()
            l_val = left.get_int() if isinstance(left, Value) else int(left)
            r_val = right.get_int() if isinstance(right, Value) else int(right)
            if op.type == LexToken.TokenLessThan: res = 1 if l_val < r_val else 0
            elif op.type == LexToken.TokenGreaterThan: res = 1 if l_val > r_val else 0
            elif op.type == LexToken.TokenLessEqual: res = 1 if l_val <= r_val else 0
            else: res = 1 if l_val >= r_val else 0
            left = Value(self.ps.types.type_int, res)
        return left

    def parse_shift(self):
        left = self.parse_additive()
        while self.ps.peek_token().type in (LexToken.TokenShiftLeft, LexToken.TokenShiftRight):
            op = self.ps.match_token()
            right = self.parse_additive()
            l_val = left.get_int() if isinstance(left, Value) else int(left)
            r_val = right.get_int() if isinstance(right, Value) else int(right)
            res = (l_val << r_val) if op.type == LexToken.TokenShiftLeft else (l_val >> r_val)
            left = Value(self.ps.types.type_int, res)
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.ps.peek_token().type in (LexToken.TokenPlus, LexToken.TokenMinus):
            op = self.ps.match_token()
            right = self.parse_multiplicative()
            if isinstance(left.val, Pointer):
                r_num = right.get_int() if isinstance(right, Value) else int(right)
                res_ptr = (left.val + r_num) if op.type == LexToken.TokenPlus else (left.val - r_num)
                left = Value(left.typ, res_ptr)
            else:
                l_num = left.val if isinstance(left, Value) else left
                r_num = right.val if isinstance(right, Value) else right
                if isinstance(l_num, float) or isinstance(r_num, float):
                    res = (float(l_num) + float(r_num)) if op.type == LexToken.TokenPlus else (float(l_num) - float(r_num))
                    left = Value(self.ps.types.type_fp, res)
                else:
                    res = (int(l_num) + int(r_num)) if op.type == LexToken.TokenPlus else (int(l_num) - int(r_num))
                    left = Value(self.ps.types.type_int, res)
        return left

    def parse_multiplicative(self):
        left = self.parse_cast()
        while self.ps.peek_token().type in (LexToken.TokenAsterisk, LexToken.TokenSlash, LexToken.TokenPercent):
            op = self.ps.match_token()
            right = self.parse_cast()
            l_num = left.val if isinstance(left, Value) else left
            r_num = right.val if isinstance(right, Value) else right
            if isinstance(l_num, float) or isinstance(r_num, float):
                if op.type == LexToken.TokenAsterisk: res = float(l_num) * float(r_num)
                elif op.type == LexToken.TokenSlash: res = float(l_num) / float(r_num) if float(r_num) != 0 else 0.0
                else: res = float(l_num) % float(r_num)
                left = Value(self.ps.types.type_fp, res)
            else:
                l_int = int(l_num) if isinstance(l_num, (int, float)) else 0
                r_int = int(r_num) if isinstance(r_num, (int, float)) else 1
                if op.type == LexToken.TokenAsterisk: res = l_int * r_int
                elif op.type == LexToken.TokenSlash: res = l_int // r_int if r_int != 0 else 0
                else: res = l_int % r_int if r_int != 0 else 0
                left = Value(self.ps.types.type_int, res)
        return left

    def parse_cast(self):
        if self.ps.peek_token().type == LexToken.TokenOpenBracket and self.ps.is_type_token(1):
            self.ps.match_token()
            cast_t = self.ps.parse_type()
            self.ps.expect(LexToken.TokenCloseBracket)
            expr = self.parse_cast()
            return self.cast_value(expr, cast_t)
        return self.parse_unary()

    def cast_value(self, val, target_type):
        raw = val.val if isinstance(val, Value) else val
        if target_type.base == BaseType.TypePointer:
            if isinstance(raw, Pointer):
                return Value(target_type, Pointer(raw.base_obj, raw.offset, target_type))
            elif isinstance(raw, (int, float)):
                return Value(target_type, Pointer(None, int(raw), target_type))
        elif target_type.base == BaseType.TypeFP:
            return Value(target_type, float(val.get_float() if isinstance(val, Value) else raw))
        elif target_type.base in (BaseType.TypeInt, BaseType.TypeShort, BaseType.TypeLong, BaseType.TypeChar):
            return Value(target_type, int(val.get_int() if isinstance(val, Value) else raw))
        return Value(target_type, raw)

    def parse_unary(self):
        tok = self.ps.peek_token()
        if tok.type == LexToken.TokenIncrement:
            self.ps.match_token()
            operand = self.parse_unary()
            return self.eval_assign(operand, Token(LexToken.TokenAddAssign, '+='), Value(self.ps.types.type_int, 1))
        elif tok.type == LexToken.TokenDecrement:
            self.ps.match_token()
            operand = self.parse_unary()
            return self.eval_assign(operand, Token(LexToken.TokenSubAssign, '-='), Value(self.ps.types.type_int, 1))
        elif tok.type == LexToken.TokenAmpersand:
            self.ps.match_token()
            operand = self.parse_unary()
            ptr_t = self.ps.types.create_pointer_type(operand.typ)
            if hasattr(operand, 'lvalue_ptr') and operand.lvalue_ptr:
                return Value(ptr_t, operand.lvalue_ptr)
            return Value(ptr_t, Pointer(operand, 0, ptr_t))
        elif tok.type == LexToken.TokenAsterisk:
            self.ps.match_token()
            operand = self.parse_unary()
            ptr_val = operand.val if isinstance(operand, Value) else operand
            if isinstance(ptr_val, Pointer):
                target_t = ptr_val.target_type.from_type if (ptr_val.target_type and ptr_val.target_type.from_type) else self.ps.types.type_int
                res = Value(target_t, ptr_val.deref(), is_lvalue=True)
                res.lvalue_ptr = ptr_val
                return res
            return Value(self.ps.types.type_int, 0)
        elif tok.type == LexToken.TokenPlus:
            self.ps.match_token()
            return self.parse_cast()
        elif tok.type == LexToken.TokenMinus:
            self.ps.match_token()
            operand = self.parse_cast()
            v = operand.val if isinstance(operand, Value) else operand
            return Value(operand.typ if isinstance(operand, Value) else self.ps.types.type_int, -v)
        elif tok.type == LexToken.TokenLogicalNot:
            self.ps.match_token()
            operand = self.parse_cast()
            v = operand.get_int() if isinstance(operand, Value) else bool(operand)
            return Value(self.ps.types.type_int, 0 if v else 1)
        elif tok.type == LexToken.TokenBitwiseNot:
            self.ps.match_token()
            operand = self.parse_cast()
            v = operand.get_int() if isinstance(operand, Value) else int(operand)
            return Value(self.ps.types.type_int, ~v)
        elif tok.type == LexToken.TokenSizeof:
            self.ps.match_token()
            if self.ps.peek_token().type == LexToken.TokenOpenBracket and self.ps.is_type_token(1):
                self.ps.match_token()
                t = self.ps.parse_type()
                self.ps.expect(LexToken.TokenCloseBracket)
                return Value(self.ps.types.type_int, t.sizeof)
            else:
                operand = self.parse_unary()
                sz = operand.typ.sizeof if isinstance(operand, Value) else 4
                return Value(self.ps.types.type_int, sz)
        return self.parse_postfix()

    def parse_postfix(self):
        left = self.parse_primary()
        while True:
            tok = self.ps.peek_token()
            if tok.type == LexToken.TokenOpenBracket:
                self.ps.match_token()
                args = []
                if self.ps.peek_token().type != LexToken.TokenCloseBracket:
                    while True:
                        args.append(self.parse_expression())
                        if self.ps.peek_token().type == LexToken.TokenComma:
                            self.ps.match_token()
                        else:
                            break
                self.ps.expect(LexToken.TokenCloseBracket)
                left = self.ps.call_function(left, args)
            elif tok.type == LexToken.TokenLeftSquareBracket:
                self.ps.match_token()
                idx_val = self.parse_expression()
                self.ps.expect(LexToken.TokenRightSquareBracket)
                idx = idx_val.get_int() if isinstance(idx_val, Value) else int(idx_val)

                if isinstance(left.val, list):
                    elem = left.val[idx] if 0 <= idx < len(left.val) else 0
                    elem_type = left.typ.from_type if left.typ.from_type else self.ps.types.type_int
                    v_obj = Value(elem_type, elem, is_lvalue=True)
                    v_obj.lvalue_ptr = Pointer(left.val, idx, elem_type)
                    left = v_obj
                elif isinstance(left.val, Pointer):
                    p = left.val + idx
                    elem_type = left.typ.from_type if left.typ.from_type else self.ps.types.type_int
                    v_obj = Value(elem_type, p.deref(), is_lvalue=True)
                    v_obj.lvalue_ptr = p
                    left = v_obj
                else:
                    left = Value(self.ps.types.type_int, 0)
            elif tok.type == LexToken.TokenDot:
                self.ps.match_token()
                member_name = self.ps.expect(LexToken.TokenIdentifier).value
                struct_val = left.val if isinstance(left, Value) else left
                base_buf = struct_val.val if isinstance(struct_val, Value) else struct_val
                if isinstance(base_buf, bytearray) and left.typ.members:
                    if member_name in left.typ.members:
                        m_type, m_offset = left.typ.members[member_name]
                        ptr = Pointer(base_buf, m_offset, self.ps.types.create_pointer_type(m_type))
                        res = Value(m_type, ptr.deref(), is_lvalue=True)
                        res.lvalue_ptr = ptr
                        left = res
                    else:
                        left = Value(self.ps.types.type_int, 0)
                else:
                    left = Value(self.ps.types.type_int, 0)
            elif tok.type == LexToken.TokenArrow:
                self.ps.match_token()
                member_name = self.ps.expect(LexToken.TokenIdentifier).value
                ptr_val = left.val if isinstance(left, Value) else left
                if isinstance(ptr_val, Pointer):
                    base_buf = ptr_val.base_obj.val if isinstance(ptr_val.base_obj, Value) else ptr_val.base_obj
                    if isinstance(base_buf, bytearray):
                        st_type = ptr_val.target_type.from_type if ptr_val.target_type else None
                        if st_type and st_type.members and member_name in st_type.members:
                            m_type, m_offset = st_type.members[member_name]
                            ptr = Pointer(base_buf, ptr_val.offset + m_offset, self.ps.types.create_pointer_type(m_type))
                            res = Value(m_type, ptr.deref(), is_lvalue=True)
                            res.lvalue_ptr = ptr
                            left = res
                        else:
                            left = Value(self.ps.types.type_int, 0)
                    else:
                        left = Value(self.ps.types.type_int, 0)
                else:
                    left = Value(self.ps.types.type_int, 0)
            elif tok.type == LexToken.TokenIncrement:
                self.ps.match_token()
                old_val = Value(left.typ, left.val)
                self.eval_assign(left, Token(LexToken.TokenAddAssign, '+='), Value(self.ps.types.type_int, 1))
                left = old_val
            elif tok.type == LexToken.TokenDecrement:
                self.ps.match_token()
                old_val = Value(left.typ, left.val)
                self.eval_assign(left, Token(LexToken.TokenSubAssign, '-='), Value(self.ps.types.type_int, 1))
                left = old_val
            else:
                break
        return left

    def parse_primary(self):
        tok = self.ps.peek_token()
        if tok.type == LexToken.TokenIntegerConstant:
            self.ps.match_token()
            return Value(self.ps.types.type_int, tok.value)
        elif tok.type == LexToken.TokenFPConstant:
            self.ps.match_token()
            return Value(self.ps.types.type_fp, tok.value)
        elif tok.type == LexToken.TokenCharacterConstant:
            self.ps.match_token()
            return Value(self.ps.types.type_char, tok.value)
        elif tok.type == LexToken.TokenStringConstant:
            self.ps.match_token()
            s_bytes = list(tok.value.encode('utf-8') + b'\0')
            ptr = Pointer(s_bytes, 0, self.ps.types.type_char_ptr)
            return Value(self.ps.types.type_char_ptr, ptr)
        elif tok.type == LexToken.TokenIdentifier:
            self.ps.match_token()
            var = self.ps.lookup_variable(tok.value)
            if var is not None:
                return var
            builtin = self.ps.lookup_builtin(tok.value)
            if builtin is not None:
                return Value(self.ps.types.type_int, builtin)
            if tok.value in self.ps.functions:
                return Value(self.ps.types.type_int, self.ps.functions[tok.value])
            return Value(self.ps.types.type_int, 0)
        elif tok.type == LexToken.TokenOpenBracket:
            self.ps.match_token()
            expr = self.parse_expression()
            self.ps.expect(LexToken.TokenCloseBracket)
            return expr
        return Value(self.ps.types.type_int, 0)


# ==============================================================================
# PARSER & INTERPRETER STATE
# ==============================================================================

class RunMode(Enum):
    Run = auto()
    Skip = auto()
    Return = auto()
    Break = auto()
    Continue = auto()


class FunctionDef:
    def __init__(self, name, return_type, params, body_tokens):
        self.name = name
        self.return_type = return_type
        self.params = params  # list of (type, name)
        self.body_tokens = body_tokens


class ParserState:
    def __init__(self, tokens, file_name="<input>"):
        self.tokens = tokens
        self.pos = 0
        self.file_name = file_name
        self.types = TypeSystem()
        self.global_table = Table()
        self.scope_stack = [self.global_table]
        self.typedefs = {}
        self.struct_defs = {}
        self.functions = {}
        self.builtins = {}
        self.macros = {"NULL": 0}
        self.static_vars = {}
        self.labels = {}
        self.if_stack = []
        self.run_mode = RunMode.Run
        self.return_val = None
        self.current_func_name = None
        self.clib = CStdLibrary(self)
        self.builtins = self.clib.register_all()
        self.expr_parser = ExpressionParser(self)

    def current_scope(self):
        return self.scope_stack[-1]

    def push_scope(self):
        new_table = Table(parent=self.current_scope())
        self.scope_stack.append(new_table)

    def pop_scope(self):
        if len(self.scope_stack) > 1:
            self.scope_stack.pop()

    def peek_token(self, offset=0):
        if self.pos + offset < len(self.tokens):
            return self.tokens[self.pos + offset]
        return self.tokens[-1]

    def match_token(self):
        tok = self.peek_token()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def expect(self, expected_type):
        tok = self.peek_token()
        if tok.type == expected_type:
            return self.match_token()
        if tok.type == LexToken.TokenEOF:
            return tok
        return self.match_token()

    def lookup_variable(self, name):
        val = self.current_scope().get(name)
        if val is not None:
            return val
        if name in self.macros:
            macro_val = self.macros[name]
            if isinstance(macro_val, (int, float)):
                return Value(self.types.type_int, macro_val)
            elif isinstance(macro_val, str):
                s_bytes = list(macro_val.encode('utf-8') + b'\0')
                ptr = Pointer(s_bytes, 0, self.types.type_char_ptr)
                return Value(self.types.type_char_ptr, ptr)
        return None

    def lookup_builtin(self, name):
        return self.builtins.get(name, None)

    def define_variable(self, name, value):
        self.current_scope().define(name, value)

    def is_type_token(self, offset=0):
        tok = self.peek_token(offset)
        if tok.type in (
            LexToken.TokenIntType, LexToken.TokenCharType, LexToken.TokenFloatType,
            LexToken.TokenDoubleType, LexToken.TokenVoidType, LexToken.TokenShortType,
            LexToken.TokenLongType, LexToken.TokenSignedType, LexToken.TokenUnsignedType,
            LexToken.TokenStructType, LexToken.TokenUnionType, LexToken.TokenEnumType,
            LexToken.TokenTypedef, LexToken.TokenStaticType
        ):
            return True
        if tok.type == LexToken.TokenIdentifier and tok.value in self.typedefs:
            return True
        return False

    def parse_type(self):
        tok = self.peek_token()
        is_unsigned = False
        is_static = False
        base_t = None

        while tok.type in (LexToken.TokenSignedType, LexToken.TokenUnsignedType, LexToken.TokenStaticType, LexToken.TokenExternType):
            if tok.type == LexToken.TokenUnsignedType:
                is_unsigned = True
            elif tok.type == LexToken.TokenStaticType:
                is_static = True
            self.match_token()
            tok = self.peek_token()

        if tok.type == LexToken.TokenIntType:
            self.match_token()
            base_t = self.types.type_uint if is_unsigned else self.types.type_int
        elif tok.type == LexToken.TokenCharType:
            self.match_token()
            base_t = self.types.type_uchar if is_unsigned else self.types.type_char
        elif tok.type == LexToken.TokenShortType:
            self.match_token()
            base_t = self.types.type_ushort if is_unsigned else self.types.type_short
        elif tok.type == LexToken.TokenLongType:
            self.match_token()
            base_t = self.types.type_ulong if is_unsigned else self.types.type_long
        elif tok.type in (LexToken.TokenFloatType, LexToken.TokenDoubleType):
            self.match_token()
            base_t = self.types.type_fp
        elif tok.type == LexToken.TokenVoidType:
            self.match_token()
            base_t = self.types.type_void
        elif tok.type in (LexToken.TokenStructType, LexToken.TokenUnionType):
            is_union = (tok.type == LexToken.TokenUnionType)
            self.match_token()
            name_tok = self.peek_token()
            struct_name = None
            if name_tok.type == LexToken.TokenIdentifier:
                struct_name = self.match_token().value
            if self.peek_token().type == LexToken.TokenLeftBrace:
                self.match_token()
                fields = {}
                struct_size = 0
                max_align = 1
                curr_offset = 0
                while self.peek_token().type != LexToken.TokenRightBrace and self.peek_token().type != LexToken.TokenEOF:
                    field_type = self.parse_type()
                    field_name_tok = self.expect(LexToken.TokenIdentifier)
                    if self.peek_token().type == LexToken.TokenLeftSquareBracket:
                        self.match_token()
                        arr_sz_tok = self.expect(LexToken.TokenIntegerConstant)
                        self.expect(LexToken.TokenRightSquareBracket)
                        field_type = self.types.create_array_type(field_type, arr_sz_tok.value)
                    field_sz = field_type.sizeof
                    field_al = field_type.align_bytes if field_type.align_bytes > 0 else 4
                    if field_al > max_align: max_align = field_al

                    if is_union:
                        offset = 0
                        if field_sz > struct_size: struct_size = field_sz
                    else:
                        if curr_offset % field_al != 0:
                            curr_offset += field_al - (curr_offset % field_al)
                        offset = curr_offset
                        curr_offset += field_sz
                        struct_size = curr_offset

                    fields[field_name_tok.value] = (field_type, offset)
                    if self.peek_token().type == LexToken.TokenSemicolon:
                        self.match_token()
                self.expect(LexToken.TokenRightBrace)
                if struct_size % max_align != 0:
                    struct_size += max_align - (struct_size % max_align)
                st = ValueType(BaseType.TypeUnion if is_union else BaseType.TypeStruct, sizeof=struct_size, align_bytes=max_align, identifier=struct_name)
                st.members = fields
                st.is_union = is_union
                if struct_name:
                    self.struct_defs[struct_name] = st
                base_t = st
            elif struct_name and struct_name in self.struct_defs:
                base_t = self.struct_defs[struct_name]
            else:
                base_t = ValueType(BaseType.TypeUnion if is_union else BaseType.TypeStruct, sizeof=8, identifier=struct_name)
        elif tok.type == LexToken.TokenEnumType:
            self.match_token()
            enum_name = None
            if self.peek_token().type == LexToken.TokenIdentifier:
                enum_name = self.match_token().value
            if self.peek_token().type == LexToken.TokenLeftBrace:
                self.match_token()
                val_cnt = 0
                while self.peek_token().type != LexToken.TokenRightBrace and self.peek_token().type != LexToken.TokenEOF:
                    item_tok = self.expect(LexToken.TokenIdentifier)
                    if self.peek_token().type == LexToken.TokenAssign:
                        self.match_token()
                        num_tok = self.expect(LexToken.TokenIntegerConstant)
                        val_cnt = num_tok.value
                    self.define_variable(item_tok.value, Value(self.types.type_int, val_cnt))
                    val_cnt += 1
                    if self.peek_token().type == LexToken.TokenComma:
                        self.match_token()
                self.expect(LexToken.TokenRightBrace)
            base_t = self.types.type_int
        elif tok.type == LexToken.TokenIdentifier and tok.value in self.typedefs:
            self.match_token()
            base_t = self.typedefs[tok.value]

        if base_t is None:
            base_t = self.types.type_int

        if is_static:
            base_t.static_qualifier = True

        while self.peek_token().type == LexToken.TokenAsterisk:
            self.match_token()
            base_t = self.types.create_pointer_type(base_t)

        return base_t

    def parse_program(self):
        while self.pos < len(self.tokens):
            tok = self.peek_token()
            if tok.type == LexToken.TokenEOF:
                break
            if tok.type == LexToken.TokenHashDefine:
                self.match_token()
                name_tok = self.expect(LexToken.TokenIdentifier)
                val_tok = self.peek_token()
                if val_tok.type in (LexToken.TokenIntegerConstant, LexToken.TokenFPConstant, LexToken.TokenStringConstant):
                    self.macros[name_tok.value] = self.match_token().value
                else:
                    self.macros[name_tok.value] = 1
                continue
            elif tok.type == LexToken.TokenHashInclude:
                self.match_token()
                while self.peek_token().type not in (LexToken.TokenEOF, LexToken.TokenIntType, LexToken.TokenCharType, LexToken.TokenFloatType, LexToken.TokenDoubleType, LexToken.TokenVoidType, LexToken.TokenStructType, LexToken.TokenUnionType, LexToken.TokenTypedef):
                    t = self.peek_token()
                    if t.type in (LexToken.TokenGreaterThan, LexToken.TokenStringConstant):
                        self.match_token()
                        break
                    self.match_token()
                continue
            elif tok.type == LexToken.TokenTypedef:
                self.match_token()
                t = self.parse_type()
                alias_tok = self.expect(LexToken.TokenIdentifier)
                self.typedefs[alias_tok.value] = t
                if self.peek_token().type == LexToken.TokenSemicolon:
                    self.match_token()
                continue
            elif self.is_type_token():
                self.parse_global_declaration_or_function()
            else:
                self.match_token()

        if "main" in self.functions:
            main_fn = self.functions["main"]
            self.call_function_def(main_fn, [])

    def parse_global_declaration_or_function(self):
        decl_type = self.parse_type()
        if self.peek_token().type == LexToken.TokenSemicolon:
            self.match_token()
            return

        name_tok = self.expect(LexToken.TokenIdentifier)
        fn_name = name_tok.value

        if self.peek_token().type == LexToken.TokenOpenBracket:
            self.match_token()
            params = []
            if self.peek_token().type != LexToken.TokenCloseBracket:
                while True:
                    if self.peek_token().type == LexToken.TokenEllipsis:
                        self.match_token()
                        break
                    p_type = self.parse_type()
                    p_name = None
                    if self.peek_token().type == LexToken.TokenIdentifier:
                        p_name = self.match_token().value
                    params.append((p_type, p_name))
                    if self.peek_token().type == LexToken.TokenComma:
                        self.match_token()
                    else:
                        break
            self.expect(LexToken.TokenCloseBracket)

            if self.peek_token().type == LexToken.TokenLeftBrace:
                body_tokens = self.extract_block_tokens()
                fn = FunctionDef(fn_name, decl_type, params, body_tokens)
                self.functions[fn_name] = fn
            else:
                if self.peek_token().type == LexToken.TokenSemicolon:
                    self.match_token()
        else:
            self.parse_var_init(decl_type, fn_name)

    def parse_var_init(self, decl_type, var_name):
        var_type = decl_type
        if decl_type.base in (BaseType.TypeStruct, BaseType.TypeUnion):
            buf = bytearray(decl_type.sizeof if decl_type.sizeof > 0 else 8)
            val = Value(decl_type, buf, is_lvalue=True)
            self.define_variable(var_name, val)
        elif self.peek_token().type == LexToken.TokenLeftSquareBracket:
            dims = []
            while self.peek_token().type == LexToken.TokenLeftSquareBracket:
                self.match_token()
                sz = 0
                if self.peek_token().type == LexToken.TokenIntegerConstant:
                    sz = self.match_token().value
                self.expect(LexToken.TokenRightSquareBracket)
                dims.append(sz)

            def build_nested_init(dim_idx):
                if dim_idx == len(dims) - 1:
                    d_sz = dims[dim_idx]
                    res = []
                    if self.peek_token().type == LexToken.TokenLeftBrace:
                        self.match_token()
                        while self.peek_token().type != LexToken.TokenRightBrace and self.peek_token().type != LexToken.TokenEOF:
                            v_init = self.expr_parser.parse_expression()
                            res.append(v_init.val if isinstance(v_init, Value) else v_init)
                            if self.peek_token().type == LexToken.TokenComma: self.match_token()
                        self.expect(LexToken.TokenRightBrace)
                    if d_sz == 0: d_sz = len(res)
                    while len(res) < d_sz: res.append(0)
                    return res
                else:
                    d_sz = dims[dim_idx]
                    res = []
                    if self.peek_token().type == LexToken.TokenLeftBrace:
                        self.match_token()
                        while self.peek_token().type != LexToken.TokenRightBrace and self.peek_token().type != LexToken.TokenEOF:
                            res.append(build_nested_init(dim_idx + 1))
                            if self.peek_token().type == LexToken.TokenComma: self.match_token()
                        self.expect(LexToken.TokenRightBrace)
                    if d_sz == 0: d_sz = len(res)
                    while len(res) < d_sz:
                        res.append(build_nested_init(dim_idx + 1))
                    return res

            if self.peek_token().type == LexToken.TokenAssign:
                self.match_token()
                init_data = build_nested_init(0)
            else:
                def make_empty(d_idx):
                    if d_idx == len(dims) - 1:
                        return [0] * (dims[d_idx] if dims[d_idx] > 0 else 1)
                    return [make_empty(d_idx + 1) for _ in range(dims[d_idx] if dims[d_idx] > 0 else 1)]
                init_data = make_empty(0)

            cur_t = decl_type
            for d in reversed(dims):
                cur_t = self.types.create_array_type(cur_t, len(init_data) if isinstance(init_data, list) else d)
            val = Value(cur_t, init_data, is_lvalue=True)
            self.define_variable(var_name, val)
        elif self.peek_token().type == LexToken.TokenAssign:
            self.match_token()
            init_val = self.expr_parser.parse_expression()
            raw_init = init_val.val if isinstance(init_val, Value) else init_val
            val = Value(var_type, raw_init, is_lvalue=True)
            self.define_variable(var_name, val)
        else:
            val = Value(var_type, 0, is_lvalue=True)
            self.define_variable(var_name, val)

        while self.peek_token().type == LexToken.TokenComma:
            self.match_token()
            next_name = self.expect(LexToken.TokenIdentifier).value
            self.parse_var_init(decl_type, next_name)

        if self.peek_token().type == LexToken.TokenSemicolon:
            self.match_token()

    def extract_block_tokens(self):
        self.expect(LexToken.TokenLeftBrace)
        depth = 1
        block = []
        while depth > 0 and self.pos < len(self.tokens):
            tok = self.match_token()
            if tok.type == LexToken.TokenLeftBrace:
                depth += 1
            elif tok.type == LexToken.TokenRightBrace:
                depth -= 1
                if depth == 0:
                    break
            block.append(tok)
        return block

    def parse_statement(self):
        tok = self.peek_token()
        if tok.type == LexToken.TokenEOF:
            return

        # Preprocessor directives
        if tok.type == LexToken.TokenHashIf:
            self.match_token()
            cond = self.expr_parser.parse_expression()
            c_val = cond.get_int() if isinstance(cond, Value) else bool(cond)
            self.if_stack.append(bool(c_val))
            return
        elif tok.type == LexToken.TokenHashIfdef:
            self.match_token()
            name_tok = self.expect(LexToken.TokenIdentifier)
            self.if_stack.append(name_tok.value in self.macros)
            return
        elif tok.type == LexToken.TokenHashIfndef:
            self.match_token()
            name_tok = self.expect(LexToken.TokenIdentifier)
            self.if_stack.append(name_tok.value not in self.macros)
            return
        elif tok.type == LexToken.TokenHashElse:
            self.match_token()
            if self.if_stack:
                last = self.if_stack.pop()
                self.if_stack.append(not last)
            return
        elif tok.type == LexToken.TokenHashEndif:
            self.match_token()
            if self.if_stack:
                self.if_stack.pop()
            return

        if self.if_stack and not all(self.if_stack):
            self.match_token()
            return

        # Skip mode handling
        if self.run_mode == RunMode.Skip:
            if tok.type == LexToken.TokenLeftBrace:
                self.extract_block_tokens()
            else:
                depth = 0
                while self.pos < len(self.tokens):
                    t = self.peek_token()
                    if t.type == LexToken.TokenEOF:
                        break
                    if t.type in (LexToken.TokenOpenBracket, LexToken.TokenLeftBrace):
                        depth += 1
                    elif t.type in (LexToken.TokenCloseBracket, LexToken.TokenRightBrace):
                        if depth == 0:
                            break
                        depth -= 1
                    elif t.type == LexToken.TokenSemicolon and depth == 0:
                        self.match_token()
                        break
                    self.match_token()
            return

        # Goto label definition identifier:
        if tok.type == LexToken.TokenIdentifier and self.peek_token(1).type == LexToken.TokenColon:
            self.match_token() # ident
            self.match_token() # :
            return

        if tok.type == LexToken.TokenGoto:
            self.match_token()
            label_tok = self.expect(LexToken.TokenIdentifier)
            if label_tok.value in self.labels:
                self.pos = self.labels[label_tok.value]
                self.run_mode = RunMode.Run
            if self.peek_token().type == LexToken.TokenSemicolon:
                self.match_token()
            return

        if tok.type == LexToken.TokenLeftBrace:
            self.push_scope()
            self.match_token()
            while self.peek_token().type != LexToken.TokenRightBrace and self.peek_token().type != LexToken.TokenEOF:
                if self.run_mode in (RunMode.Break, RunMode.Return, RunMode.Continue):
                    break
                self.parse_statement()
            self.expect(LexToken.TokenRightBrace)
            self.pop_scope()
            return

        if tok.type == LexToken.TokenIf:
            self.match_token()
            self.expect(LexToken.TokenOpenBracket)
            cond = self.expr_parser.parse_expression()
            self.expect(LexToken.TokenCloseBracket)

            parent_mode = self.run_mode
            cond_val = bool(cond.get_int() if isinstance(cond, Value) else cond) if parent_mode == RunMode.Run else False

            if cond_val:
                self.run_mode = parent_mode
                self.parse_statement()
                if self.peek_token().type == LexToken.TokenElse:
                    self.match_token()
                    self.run_mode = RunMode.Skip
                    self.parse_statement()
                    self.run_mode = parent_mode
            else:
                self.run_mode = RunMode.Skip
                self.parse_statement()
                if self.peek_token().type == LexToken.TokenElse:
                    self.match_token()
                    self.run_mode = parent_mode
                    self.parse_statement()
                else:
                    self.run_mode = parent_mode
            return

        if tok.type == LexToken.TokenSwitch:
            self.match_token()
            self.expect(LexToken.TokenOpenBracket)
            switch_val = self.expr_parser.parse_expression().get_int()
            self.expect(LexToken.TokenCloseBracket)
            switch_block = self.extract_block_tokens()

            sub = ParserState(switch_block + [Token(LexToken.TokenEOF, None)], self.file_name)
            sub.global_table = self.global_table
            sub.scope_stack = self.scope_stack
            sub.functions = self.functions
            sub.struct_defs = self.struct_defs
            sub.typedefs = self.typedefs
            sub.macros = self.macros
            sub.builtins = self.builtins
            sub.types = self.types

            cases = {}
            default_idx = None
            i = 0
            while i < len(switch_block):
                if switch_block[i].type == LexToken.TokenCase:
                    c_val = switch_block[i+1].value if i+1 < len(switch_block) else 0
                    cases[c_val] = i + 3
                elif switch_block[i].type == LexToken.TokenDefault:
                    default_idx = i + 2
                i += 1

            start_idx = cases.get(switch_val, default_idx)
            if start_idx is not None:
                sub.pos = start_idx
                while sub.pos < len(sub.tokens) and sub.peek_token().type != LexToken.TokenEOF:
                    if sub.run_mode == RunMode.Break:
                        break
                    t = sub.peek_token()
                    if t.type in (LexToken.TokenCase, LexToken.TokenDefault):
                        sub.match_token()
                        if t.type == LexToken.TokenCase:
                            sub.expr_parser.parse_expression()
                        sub.expect(LexToken.TokenColon)
                        continue
                    sub.parse_statement()
            return

        if tok.type == LexToken.TokenWhile:
            self.match_token()
            cond_pos = self.pos
            while True:
                self.pos = cond_pos
                self.expect(LexToken.TokenOpenBracket)
                cond = self.expr_parser.parse_expression()
                self.expect(LexToken.TokenCloseBracket)
                cond_val = cond.get_int() if isinstance(cond, Value) else bool(cond)
                if not cond_val or self.run_mode != RunMode.Run:
                    old_mode = self.run_mode
                    self.run_mode = RunMode.Skip
                    self.parse_statement()
                    self.run_mode = old_mode
                    break
                self.parse_statement()
                if self.run_mode == RunMode.Break:
                    self.run_mode = RunMode.Run
                    break
                elif self.run_mode == RunMode.Continue:
                    self.run_mode = RunMode.Run
            return

        if tok.type == LexToken.TokenDo:
            self.match_token()
            body_pos = self.pos
            while True:
                self.pos = body_pos
                self.parse_statement()
                if self.run_mode == RunMode.Break:
                    self.run_mode = RunMode.Run
                    break
                elif self.run_mode == RunMode.Continue:
                    self.run_mode = RunMode.Run
                self.expect(LexToken.TokenWhile)
                self.expect(LexToken.TokenOpenBracket)
                cond = self.expr_parser.parse_expression()
                self.expect(LexToken.TokenCloseBracket)
                if self.peek_token().type == LexToken.TokenSemicolon:
                    self.match_token()
                cond_val = cond.get_int() if isinstance(cond, Value) else bool(cond)
                if not cond_val:
                    break
            return

        if tok.type == LexToken.TokenFor:
            self.match_token()
            self.expect(LexToken.TokenOpenBracket)
            self.push_scope()
            if self.peek_token().type != LexToken.TokenSemicolon:
                if self.is_type_token():
                    self.parse_declaration()
                else:
                    self.expr_parser.parse_expression()
            if self.peek_token().type == LexToken.TokenSemicolon:
                self.match_token()

            cond_pos = self.pos
            while True:
                self.pos = cond_pos
                cond_val = True
                if self.peek_token().type != LexToken.TokenSemicolon:
                    c = self.expr_parser.parse_expression()
                    cond_val = c.get_int() if isinstance(c, Value) else bool(c)
                if self.peek_token().type == LexToken.TokenSemicolon:
                    self.match_token()

                incr_pos = self.pos
                bracket_cnt = 0
                while self.pos < len(self.tokens):
                    t = self.peek_token()
                    if t.type == LexToken.TokenOpenBracket: bracket_cnt += 1
                    elif t.type == LexToken.TokenCloseBracket:
                        if bracket_cnt == 0: break
                        bracket_cnt -= 1
                    self.match_token()
                self.expect(LexToken.TokenCloseBracket)

                if not cond_val or self.run_mode != RunMode.Run:
                    old_mode = self.run_mode
                    self.run_mode = RunMode.Skip
                    self.parse_statement()
                    self.run_mode = old_mode
                    break

                self.parse_statement()
                if self.run_mode == RunMode.Break:
                    self.run_mode = RunMode.Run
                    break
                elif self.run_mode == RunMode.Continue:
                    self.run_mode = RunMode.Run

                saved_body_end = self.pos
                self.pos = incr_pos
                if self.peek_token().type != LexToken.TokenCloseBracket:
                    self.expr_parser.parse_expression()
                self.pos = saved_body_end
            self.pop_scope()
            return

        if tok.type == LexToken.TokenReturn:
            self.match_token()
            if self.peek_token().type != LexToken.TokenSemicolon:
                self.return_val = self.expr_parser.parse_expression()
            if self.peek_token().type == LexToken.TokenSemicolon:
                self.match_token()
            self.run_mode = RunMode.Return
            return

        if tok.type == LexToken.TokenBreak:
            self.match_token()
            if self.peek_token().type == LexToken.TokenSemicolon:
                self.match_token()
            self.run_mode = RunMode.Break
            return

        if tok.type == LexToken.TokenContinue:
            self.match_token()
            if self.peek_token().type == LexToken.TokenSemicolon:
                self.match_token()
            self.run_mode = RunMode.Continue
            return

        if self.is_type_token():
            self.parse_declaration()
            return

        if tok.type == LexToken.TokenSemicolon:
            self.match_token()
            return

        self.expr_parser.parse_expression()
        if self.peek_token().type == LexToken.TokenSemicolon:
            self.match_token()

    def parse_declaration(self):
        decl_type = self.parse_type()
        var_name = self.expect(LexToken.TokenIdentifier).value

        if decl_type.static_qualifier:
            static_key = f"static_{self.current_func_name}_{var_name}"
            if static_key in self.static_vars:
                self.define_variable(var_name, self.static_vars[static_key])
                if self.peek_token().type == LexToken.TokenAssign:
                    self.match_token()
                    self.expr_parser.parse_expression()
                if self.peek_token().type == LexToken.TokenSemicolon:
                    self.match_token()
                return
            else:
                self.parse_var_init(decl_type, var_name)
                self.static_vars[static_key] = self.current_scope().get(var_name)
                return

        self.parse_var_init(decl_type, var_name)

    def call_function(self, fn_val, args):
        if isinstance(fn_val, Value):
            fn_val = fn_val.val
        if isinstance(fn_val, FunctionDef):
            return self.call_function_def(fn_val, args)
        elif callable(fn_val):
            res = fn_val(args)
            if isinstance(res, Value):
                return res
            return Value(self.types.type_int, res)
        return Value(self.types.type_int, 0)

    def call_function_def(self, fn_def, args):
        fn_tokens = list(fn_def.body_tokens) + [Token(LexToken.TokenEOF, None)]
        sub_parser = ParserState(fn_tokens, self.file_name)
        sub_parser.global_table = self.global_table
        sub_parser.scope_stack = [self.global_table]
        sub_parser.functions = self.functions
        sub_parser.struct_defs = self.struct_defs
        sub_parser.typedefs = self.typedefs
        sub_parser.macros = self.macros
        sub_parser.builtins = self.builtins
        sub_parser.types = self.types
        sub_parser.static_vars = self.static_vars
        sub_parser.current_func_name = fn_def.name

        labels = {}
        for idx in range(len(fn_tokens) - 1):
            if fn_tokens[idx].type == LexToken.TokenIdentifier and fn_tokens[idx+1].type == LexToken.TokenColon:
                labels[fn_tokens[idx].value] = idx + 2
        sub_parser.labels = labels

        sub_parser.push_scope()

        for i, (p_type, p_name) in enumerate(fn_def.params):
            if p_name and i < len(args):
                arg_val = args[i]
                v = arg_val.val if isinstance(arg_val, Value) else arg_val
                if p_type.base == BaseType.TypePointer and isinstance(v, list):
                    v = Pointer(v, 0, p_type)
                sub_parser.define_variable(p_name, Value(p_type, v, is_lvalue=True))

        while sub_parser.pos < len(sub_parser.tokens) and sub_parser.peek_token().type != LexToken.TokenEOF and sub_parser.run_mode == RunMode.Run:
            sub_parser.parse_statement()

        return sub_parser.return_val if sub_parser.return_val is not None else Value(self.types.type_int, 0)


# ==============================================================================
# PUBLIC INTERFACE & MAIN CLI
# ==============================================================================

def interpret_source(source_text, file_name="<input>"):
    tokens = lex_analyse(source_text, file_name)
    parser = ParserState(tokens, file_name)
    parser.parse_program()
    return parser


def main():
    if len(sys.argv) < 2:
        print("Usage: python picoc_standalone.py <file.c> | -c 'code'", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "-c":
        if len(sys.argv) < 3:
            print("Error: -c option requires source code argument", file=sys.stderr)
            sys.exit(1)
        source = sys.argv[2]
        interpret_source(source, "<inline>")
    else:
        file_path = sys.argv[1]
        if not os.path.exists(file_path):
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
        interpret_source(source, file_path)


if __name__ == "__main__":
    main()
