import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CP_HOME = os.path.join(REPO, "stage-claude", "00-install", "files", "rootfs", "opt", "kistengeist")
MODULES_DIR = os.path.join(CP_HOME, "modules")

sys.path.insert(0, os.path.join(CP_HOME, "wizard"))
sys.path.insert(0, os.path.join(CP_HOME, "lib"))
