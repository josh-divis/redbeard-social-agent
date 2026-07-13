#!/usr/bin/env python3
"""
Thin entrypoint so operators can run:

    python main.py generate
    python main.py dashboard

Prefer: python -m agent.cli <command>
"""

from agent.cli import main

if __name__ == "__main__":
    main()
