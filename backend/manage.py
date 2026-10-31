#!/usr/bin/env python
"""Django management entry point for the EgoHand Twin backend."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "egohand_backend.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
