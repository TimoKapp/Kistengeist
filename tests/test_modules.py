import os

import pytest
from conftest import MODULES_DIR

import modules as modlib


@pytest.fixture(scope="module")
def mods():
    return modlib.load_modules(MODULES_DIR)


def test_every_module_has_install_script(mods):
    for mid in mods:
        assert os.path.isfile(os.path.join(MODULES_DIR, mid, "install.sh")), mid


def test_required_modules_per_mode(mods):
    desktop = modlib.plan(mods, "desktop", [])
    rdp = modlib.plan(mods, "rdp", [])
    both = modlib.plan(mods, "both", [])
    for plan in (desktop, rdp, both):
        assert plan[0] == "base"
        assert plan[-1] == "finalize"
        assert "claude-desktop" in plan and "session" in plan
    assert "display-local" in desktop and "remote-rdp" not in desktop
    assert "remote-rdp" in rdp and "display-local" not in rdp
    assert "display-local" in both and "remote-rdp" in both


def test_dependencies_are_added(mods):
    plan = modlib.plan(mods, "rdp", ["claude-in-chrome"])
    assert plan.index("chrome") < plan.index("claude-in-chrome")


def test_mode_specific_module_is_dropped(mods):
    assert "energy" not in modlib.plan(mods, "rdp", ["energy"])
    assert "energy" in modlib.plan(mods, "desktop", ["energy"])


def test_unknown_module_and_mode_rejected(mods):
    with pytest.raises(modlib.PlanError):
        modlib.plan(mods, "desktop", ["gibt-es-nicht"])
    with pytest.raises(modlib.PlanError):
        modlib.plan(mods, "kiosk", [])


def test_plan_is_ordered_and_unique(mods):
    everything = [m for m in mods if not mods[m].required]
    plan = modlib.plan(mods, "both", everything)
    assert len(plan) == len(set(plan))
    orders = [mods[m].order for m in plan]
    assert orders == sorted(orders)
    # Firewall nach allen Modulen, die Ports brauchen; Abschluss ganz am Ende.
    assert plan.index("firewall") > plan.index("remote-rdp")
    assert plan.index("firewall") > plan.index("ssh")


def test_parse_conf_handles_quotes_and_comments():
    conf = modlib.parse_conf('# x\nA="eins zwei"\nB=drei\n\nC=\'vier\'\nkaputt\n')
    assert conf == {"A": "eins zwei", "B": "drei", "C": "vier"}


def test_cli_plan(tmp_path, capsys):
    setup = tmp_path / "setup.conf"
    setup.write_text('MODE="desktop"\nMODULES="files storage"\n')
    assert modlib.main(["plan", "--modules-dir", MODULES_DIR, "--setup", str(setup)]) == 0
    out = capsys.readouterr().out.split()
    assert "files" in out and "storage" in out


def test_cli_plan_rejects_bad_mode(tmp_path):
    setup = tmp_path / "setup.conf"
    setup.write_text('MODE="nix"\n')
    assert modlib.main(["plan", "--modules-dir", MODULES_DIR, "--setup", str(setup)]) == 1
