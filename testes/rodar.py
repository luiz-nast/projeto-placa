"""roda a bateria inteira do Sianvolt: python3 testes/rodar.py (melhor com o .venv, que tem o gerbonara)"""
import sys
import unittest
from pathlib import Path

if __name__ == "__main__":
    aqui = Path(__file__).resolve().parent
    sys.path.insert(0, str(aqui))
    resultado = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(aqui)))
    sys.exit(0 if resultado.wasSuccessful() else 1)
