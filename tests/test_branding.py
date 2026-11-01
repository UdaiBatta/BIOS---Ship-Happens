"""The renamed package preserves existing private environment configuration."""
import os
import subprocess
import sys


def test_legacy_settings_are_accepted_and_explicit_new_settings_win():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EGOHAND_", "MOTIONIQ_"))}
    env.update(EGOHAND_API_TOKEN="synthetic-test-token", EGOHAND_DATA_DIR="legacy-private-dir",
               EGOHAND_DEBUG="1", MOTIONIQ_DEBUG="0")
    subprocess.run([sys.executable, "-c", "import motioniq, os; "
                    "assert os.environ['MOTIONIQ_API_TOKEN'] == 'synthetic-test-token'; "
                    "assert os.environ['MOTIONIQ_DATA_DIR'] == 'legacy-private-dir'; "
                    "assert os.environ['MOTIONIQ_DEBUG'] == '0'"], env=env, check=True)
