"""Fixture: print() suppressed via inline waiver — zero diagnostics."""


def main() -> None:
    print("hi")  # canonical: ignore py-print-smoke — bootstrap script (#7458)
