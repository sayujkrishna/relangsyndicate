# Wren - Python Implementation

This is a Python 3 implementation of the Wren programming language interpreter, created for the **reLang — Language Migration Hackathon**.

## Prerequisites

- Python 3.12+ (standard library only, no external dependencies required)

## Build

No compilation step required for Python.

## Run

```bash
python3 ../target/wren.py <path-to-wren-file>
```

On Windows (with Python 3.12+):
```powershell
python ../target/wren.py <path-to-wren-file>
```

## Local Validation

From the `relang/` directory:

```bash
python3 validate.py "python3 ../target/wren.py"
```

## Structure

- `wren.py` - Main CLI entry point
- `wren_lexer.py` - Lexical scanner and tokenizer
- `wren_ast.py` - Abstract Syntax Tree node definitions
- `wren_parser.py` - Precedence and recursive descent parser
- `wren_interpreter.py` - Execution engine and method dispatch system
- `wren_core.py` - Core object system and built-in classes (`Object`, `String`, `List`, `Map`, `Fiber`, `Fn`, etc.)
- `wren_modules.py` - Standard library module bindings (`io`, `os`, `timer`, `scheduler`)
