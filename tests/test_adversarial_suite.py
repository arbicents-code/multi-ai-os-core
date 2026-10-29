"""Top-level alias runner for the T01-T12 Adversarial Red-Team Suite (`AGENTS.md` §3)."""

from tests.adversarial.test_t01_to_t12 import TestAdversarialSuiteT01ToT12

__all__ = ["TestAdversarialSuiteT01ToT12"]

if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
