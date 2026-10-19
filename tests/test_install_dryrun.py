"""Führt den echten Installer im Testmodus aus (Befehle werden nur protokolliert)."""

import json
import os
import subprocess

import pytest
from conftest import CP_HOME

INSTALLER = os.path.join(CP_HOME, "bin", "kistengeist-install")

XRDP_INI = "[Globals]\nport=3389\n\n[Xorg]\nname=Xorg\nlib=libxup.so\n"


def run_install(tmp_path, mode, modules, autologin="yes", secret=True, extra_conf=""):
    root = tmp_path / "root"
    (root / "etc" / "kistengeist").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "xrdp").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "xrdp" / "xrdp.ini").write_text(XRDP_INI)
    (root / "etc" / "pam.d").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "pam.d" / "xrdp-sesman").write_text("@include common-auth\n")
    (root / "etc" / "ufw").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "ufw" / "ufw.conf").write_text("ENABLED=no\nLOGLEVEL=low\n")
    (root / "boot" / "firmware").mkdir(parents=True, exist_ok=True)
    (root / "boot" / "firmware" / "config.txt").write_text("[all]\n")
    (root / "tmp").mkdir(exist_ok=True)
    (root / "etc" / "kistengeist" / "setup.conf").write_text(
        f'MODE="{mode}"\nAUTOLOGIN="{autologin}"\nMODULES="{" ".join(modules)}"\n'
        'TIMEZONE="Europe/Berlin"\nKEYMAP="de"\nLOCALE="de_DE.UTF-8"\n' + extra_conf
    )
    (root / "etc" / "kistengeist" / "legal-accepted").write_text("VERSION=test\n")
    if secret:
        (root / "run" / "kistengeist").mkdir(parents=True, exist_ok=True)
        (root / "run" / "kistengeist" / "secret").write_text("geheim123\n")
    env = {**os.environ, "CP_ROOT": str(root), "CP_DRY_RUN": "1", "CP_HOME_DIR": CP_HOME}
    result = subprocess.run(["bash", INSTALLER], env=env, capture_output=True, text=True)
    return root, result


def status(root):
    return json.loads((root / "run" / "kistengeist" / "status.json").read_text())


def test_desktop_mode(tmp_path):
    root, result = run_install(tmp_path, "desktop", ["chrome", "claude-in-chrome", "energy"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert status(root)["state"] == "done"
    lightdm = (root / "etc/lightdm/lightdm.conf.d/50-kistengeist.conf").read_text()
    assert "autologin-user=claude" in lightdm and "user-session=kistengeist" in lightdm
    assert (root / "etc/X11/xorg.conf.d/99-vc4.conf").exists()
    assert "fcoeoabgfenejglbffodgkkbkcdhcgfn" in (root / "etc/opt/chrome/policies/managed/kistengeist.json").read_text()
    assert "SCREEN_OFF_SECONDS=600" in (root / "etc/kistengeist/energy.conf").read_text()
    assert (root / "etc/kistengeist/installed").exists()
    assert (root / "etc/xrdp/xrdp.ini").read_text() == XRDP_INI  # RDP nicht gewählt
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "set-default graphical.target" in log
    assert "3389" not in log


def test_rdp_mode(tmp_path):
    root, result = run_install(tmp_path, "rdp", ["ssh", "firewall"], autologin="no", secret=False)
    assert result.returncode == 0, result.stdout + result.stderr
    ini = (root / "etc/xrdp/xrdp.ini").read_text()
    assert "[Kistengeist]" in ini and "[Xorg]" not in ini
    assert "kistengeist-session" in (root / "etc/xrdp/startwm.sh").read_text()
    assert "pam_gnome_keyring" in (root / "etc/pam.d/xrdp-sesman").read_text()
    assert not (root / "etc/lightdm").exists()
    assert "ENABLED=yes" in (root / "etc/ufw/ufw.conf").read_text()
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "ufw allow from 192.168.0.0/16 to any port 3389 proto tcp" in log       # RDP nur Heimnetz
    assert "ufw allow from 192.168.0.0/16 to any port 22 proto tcp" in log         # SSH nur Heimnetz
    assert "set-default multi-user.target" in log
    assert "pipewire pipewire-bin pipewire-pulse wireplumber pipewire-module-xrdp" in log  # Ton/Mikro über RDP
    assert "gtk-double-click-time=800" in (root / "home/claude/.config/gtk-3.0/settings.ini").read_text()


def test_both_mode_consumes_secret(tmp_path):
    root, result = run_install(tmp_path, "both", ["files", "storage"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[Kistengeist-Bildschirm]" in (root / "etc/xrdp/xrdp.ini").read_text()
    assert not (root / "run/kistengeist/secret").exists()
    assert (root / "etc/sudoers.d/kistengeist-storage").exists()
    assert oct(os.stat(root / "etc/sudoers.d/kistengeist-storage").st_mode & 0o777) == "0o440"
    assert (root / "etc/polkit-1/rules.d/50-kistengeist-udisks.rules").exists()


def test_both_mode_without_secret_fails(tmp_path):
    root, result = run_install(tmp_path, "both", [], secret=False)
    assert result.returncode != 0
    st = status(root)
    assert st["state"] == "failed" and st["module"] == "remote-rdp"


@pytest.mark.parametrize("module", ["cowork", "bluetooth-off", "auto-updates", "sd-protect", "claude-code"])
def test_optional_modules_run(tmp_path, module):
    root, result = run_install(tmp_path, "desktop", [module])
    assert result.returncode == 0, result.stdout + result.stderr


def test_bluetooth_off_edits_config(tmp_path):
    root, _ = run_install(tmp_path, "desktop", ["bluetooth-off"])
    assert "dtoverlay=disable-bt" in (root / "boot/firmware/config.txt").read_text()


def test_code_and_upload_launchers(tmp_path):
    root, result = run_install(tmp_path, "desktop", ["upload", "firewall"])
    assert result.returncode == 0, result.stdout + result.stderr
    apps = root / "opt/kistengeist/share/applications"
    assert "kistengeist-launch code" in (apps / "kistengeist-code.desktop").read_text()
    assert "kistengeist-launch upload" in (apps / "kistengeist-upload.desktop").read_text()
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "ufw allow from 192.168.0.0/16 to any port 8765 proto tcp" in log


def test_upload_port_closed_without_module(tmp_path):
    root, _ = run_install(tmp_path, "desktop", ["firewall"])
    assert "8765" not in (root / "var/log/kistengeist/install.log").read_text()


def test_remote_control_module(tmp_path):
    import json as _json

    root, result = run_install(tmp_path, "rdp", ["remote-control"], autologin="no", secret=False)
    assert result.returncode == 0, result.stdout + result.stderr
    home = root / "home/claude"
    settings = _json.loads((home / ".claude/settings.json").read_text())
    assert settings["remoteControlAtStartup"] is True
    assert settings["agentPushNotifEnabled"] is True and settings["inputNeededNotifEnabled"] is True
    trust = _json.loads((home / ".claude.json").read_text())
    assert trust["projects"]["/home/claude/Projekte"]["hasTrustDialogAccepted"] is True
    unit = (root / "etc/systemd/user/kistengeist-remote.service").read_text()
    assert "ExecStart=/opt/kistengeist/bin/kistengeist-remote" in unit and "Restart=always" in unit
    link = home / ".config/systemd/user/default.target.wants/kistengeist-remote.service"
    assert link.is_symlink()
    desktop = root / "opt/kistengeist/share/applications/kistengeist-mobile.desktop"
    assert "kistengeist-launch mobile" in desktop.read_text()
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "loginctl enable-linger claude" in log
    # Abhängigkeit: Claude Code wird mitinstalliert
    assert "claude-code" in log


def test_privacy_minimal_env(tmp_path):
    import json as _json

    root, result = run_install(tmp_path, "desktop", ["claude-code"])
    assert result.returncode == 0, result.stdout + result.stderr
    settings = _json.loads((root / "home/claude/.claude/settings.json").read_text())
    assert settings["env"]["DISABLE_ERROR_REPORTING"] == "1"
    assert "DISABLE_TELEMETRY" not in settings["env"]  # würde Remote Control abschalten


def test_installer_refuses_without_legal(tmp_path):
    root, _ = run_install(tmp_path / "a", "desktop", [])
    (root / "etc/kistengeist/legal-accepted").unlink()
    (root / "etc/kistengeist/installed").unlink()
    env = {**os.environ, "CP_ROOT": str(root), "CP_DRY_RUN": "1", "CP_HOME_DIR": CP_HOME}
    result = subprocess.run(["bash", INSTALLER], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and "Rechtliche Hinweise" in result.stdout + result.stderr


def test_graphify(tmp_path):
    root, result = run_install(tmp_path, "desktop", ["claude-code", "graphify"])
    assert result.returncode == 0, result.stdout + result.stderr
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "pipx python3-venv" in log
    assert "pipx install --force graphifyy[pdf]==" in log and "install --platform claude" in log
    assert log.index("claude.ai/install.sh") < log.index("pipx install")   # Claude Code zuerst


def test_terminal_panel_and_vscode(tmp_path):
    root, result = run_install(tmp_path, "desktop", ["claude-code", "terminal-panel", "vscode"])
    assert result.returncode == 0, result.stdout + result.stderr
    home = root / "home" / "claude"
    server = json.loads((home / ".config/Claude/claude_desktop_config.json").read_text())
    assert server["mcpServers"]["kistengeist-terminal"]["args"] == ["/opt/kistengeist/lib/kistengeist_terminal_mcp.py"]
    cli = json.loads((home / ".claude.json").read_text())
    assert cli["mcpServers"]["kistengeist-terminal"]["type"] == "stdio"
    assert oct(os.stat(home / ".claude.json").st_mode & 0o777) == "0o600"
    assert json.loads((home / ".vscode/argv.json").read_text())["password-store"] == "gnome-libsecret"
    assert json.loads((home / ".config/Code/User/settings.json").read_text())["telemetry.telemetryLevel"] == "off"
    assert (root / "etc/apt/sources.list.d/vscode.sources").exists()
    assert (root / "opt/kistengeist/share/applications/kistengeist-terminal.desktop").exists()
    assert (root / "opt/kistengeist/share/applications/kistengeist-vscode.desktop").exists()
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "--install-extension anthropic.claude-code" in log
    assert "tmux xterm xclip wmctrl" in log


def test_server_n8n_usb_and_access_file(tmp_path):
    root = tmp_path / "root"
    (root / "etc" / "kistengeist").mkdir(parents=True)
    (root / "etc" / "kistengeist" / "ddns.json").write_text('{"token": "ipv64-token-1234"}')
    (root / "run" / "kistengeist").mkdir(parents=True)
    (root / "run" / "kistengeist" / "n8n.json").write_text(json.dumps(
        {"firstName": "T", "lastName": "X", "email": "t@example.org", "password": "Geheim123", "license": ""}))
    (root / "run" / "kistengeist" / "account.secret").write_text("geheim123\n")
    (root / "etc" / "fstab").write_text("proc /proc proc defaults 0 0\n")
    extra = ('USB_DEVICE="/dev/disk/by-id/usb-SanDisk-0:0"\nUSB_FORMAT="yes"\nUSB_LABEL="KISTENGEIST"\n'
             'NET_ACCESS="dyndns"\nDDNS_PROVIDER="ipv64"\nDDNS_HOST="meinpi.ipv64.net"\nACME_EMAIL="t@example.org"\n'
             'ACCESS_FILE_SECRETS="yes"\nACCESS_FILE_USB="yes"\n')
    root2, result = run_install(tmp_path, "desktop", ["usb-stick", "webserver", "n8n", "zugangsdaten", "firewall"],
                                extra_conf=extra)
    assert result.returncode == 0, result.stdout + result.stderr
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "mkfs.exfat -L KISTENGEIST /dev/sdx1" in log and "wipefs -a /dev/sdx" in log
    fstab = (root / "etc/fstab").read_text()
    assert "/mnt/usb-stick exfat" in fstab and "nofail" in fstab and "uid=" in fstab and "proc /proc" in fstab
    caddy = (root / "etc/caddy/Caddyfile").read_text()
    assert "meinpi.ipv64.net {" in caddy and "reverse_proxy 127.0.0.1:5678" in caddy
    assert "email t@example.org" in caddy
    assert "kistengeist-ddns --force" in log and (root / "etc/systemd/system/kistengeist-ddns.timer").exists()
    compose = (root / "srv/n8n/docker-compose.yml").read_text()
    assert "n8nio/n8n:stable" in compose and "127.0.0.1:5678:5678" in compose
    env = (root / "srv/n8n/n8n.env").read_text()
    assert "N8N_WEBHOOK_URL=https://meinpi.ipv64.net/" in env and "N8N_PROXY_HOPS=1" in env
    assert "N8N_DIAGNOSTICS_ENABLED=false" in env and "WEBHOOK_URL=" not in env.replace("N8N_WEBHOOK_URL=", "")
    assert oct(os.stat(root / "srv/n8n/n8n.env").st_mode & 0o777) == "0o600"
    acc = json.loads((root / "etc/kistengeist/access.json").read_text())
    assert acc["public_url"] == "https://meinpi.ipv64.net" and acc["n8n_owner"] == "ok"
    cli = json.loads((root / "home/claude/.claude.json").read_text())
    assert cli["mcpServers"]["n8n"]["url"] == "https://meinpi.ipv64.net/mcp-server/http"
    z = (root / "home/claude/Zugangsdaten.txt").read_text()
    assert "Geheim123" in z and "FREIGEBEN" in z and "meinpi.ipv64.net" in z
    assert oct(os.stat(root / "home/claude/Zugangsdaten.txt").st_mode & 0o777) == "0o600"
    assert (root / "mnt/usb-stick/Zugangsdaten.txt").exists()
    assert not (root / "run/kistengeist/n8n.json").exists() and not (root / "run/kistengeist/account.secret").exists()
    assert "ufw allow 443/tcp" in log and "ufw allow 80/tcp" in log
    assert "docker.io docker-cli docker-compose" in log  # Befehl "docker" (Rückmeldung vom Pi)
    assert (root / "home/claude/USB-Stick").is_symlink()
    assert not (root / "home/claude/Kistengeist.rdp").exists()   # Modus desktop: keine RDP-Datei
    assert 'USB_FORMAT="no"' in (root / "etc/kistengeist/setup.conf").read_text()  # nur einmal formatieren
    dropin = root / "etc/systemd/system/caddy.service.d/kistengeist.conf"
    assert "ConditionPathExists=/etc/kistengeist/installed" in dropin.read_text()
    assert "OWNER" not in env and "kistengeist-owner" not in (root / "srv/n8n/n8n.env").read_text()
    assert "kistengeist-n8n firewall" in (root / "etc/systemd/system/kistengeist-n8n.service").read_text()


@pytest.mark.parametrize("mode", ["rdp", "both"])
def test_browser_remote_access(tmp_path, mode):
    root, result = run_install(tmp_path, mode, ["firewall"], autologin="yes", secret=True,
                               extra_conf='REMOTE="browser"\n')
    assert result.returncode == 0, result.stdout + result.stderr
    log = (root / "var/log/kistengeist/install.log").read_text()
    assert "selkies-2.0.0-debiantrixie-arm64.deb" in log
    assert "xrdp" not in log.replace("xrdp-", "")          # kein RDP installiert
    assert "port 8443" in log and "3389" not in log           # Firewall: Browser nur Heimnetz
    env = root / "home/claude/.config/kistengeist/selkies.env"
    assert 'SELKIES_BASIC_AUTH_PASSWORD="geheim123"' in env.read_text()
    assert oct(os.stat(env).st_mode & 0o777) == "0o600"
    assert (root / "etc/systemd/user/kistengeist-selkies.service").exists()
    assert (root / "var/lib/systemd/linger/claude").exists()
    conf = (root / "etc/kistengeist/selkies.conf").read_text()
    if mode == "rdp":
        assert (root / "etc/systemd/user/kistengeist-xvfb.service").exists() and "RESIZE=true" in conf
    else:
        assert not (root / "etc/systemd/user/kistengeist-xvfb.service").exists() and "RESIZE=false" in conf


USER_DATA = """#cloud-config
hostname: kistengeist
write_files:
  - path: /etc/kistengeist/setup-code
    permissions: '0600'
    content: |
      K7M2Q9XAPR
  - path: /usr/local/sbin/kistengeist-firstboot
    permissions: '0755'
    content: |
      #!/bin/bash
      KG_START_CONSOLE=1 bash /root/kistengeist-install.sh
runcmd:
  - [systemctl, start, --no-block, kistengeist-firstboot.service]
"""
NETWORK = """network:
  version: 2
  wifis:
    wlan0:
      access-points:
        "MeinWLAN":
            password: "geheim123"
"""


def test_finalize_removes_setup_secrets(tmp_path):
    root = tmp_path / "root"
    fw = root / "boot" / "firmware"
    fw.mkdir(parents=True)
    (fw / "user-data").write_text(USER_DATA)
    (fw / "network-config").write_text(NETWORK)
    (root / "etc" / "netplan").mkdir(parents=True)
    (root / "etc" / "netplan" / "50-cloud-init.yaml").write_text(NETWORK)
    (root / "etc" / "kistengeist").mkdir(parents=True)
    (root / "etc" / "kistengeist" / "setup-code").write_text("K7M2Q9XAPR\n")
    root2, result = run_install(tmp_path, "desktop", ["claude-desktop"])
    assert result.returncode == 0, result.stdout + result.stderr
    ud = (fw / "user-data").read_text()
    assert "K7M2Q9XAPR" not in ud and "kistengeist-firstboot" in ud and "hostname: kistengeist" in ud
    assert "geheim123" not in (fw / "network-config").read_text()
    assert "geheim123" in (root / "etc/netplan/50-cloud-init.yaml").read_text()   # WLAN läuft weiter
    assert (root / "etc/cloud/cloud-init.disabled").exists()
    assert not (root / "etc/kistengeist/setup-code").exists()
