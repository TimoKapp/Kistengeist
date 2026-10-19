# Arbeitsregeln für Kistengeist

- **Vorbild ist die originale Claude-Desktop-App.** Bevor ein Feature gebaut oder als fertig gemeldet
  wird: tief recherchieren, was die Original-App dazu kann (Desktop-Doku, Linux-Beta-Doku,
  Remote Control, Mobile/Dispatch, Help-Center-Artikel, Changelog) – und alle zugehörigen Wege
  mitdenken (z. B. Handy-Steuerung über Dispatch *und* Remote Control). Nicht bei der ersten
  Lösung stehen bleiben.
- Quellen zuerst lesen (code.claude.com/docs/llms.txt als Index, support.claude.com), Annahmen
  am Kernel/Paket prüfen (z. B. Raspberry-Pi-defconfig), nicht raten.
- **Nur fertige, kundentaugliche Lösungen:** Image installieren und alles funktioniert – keine
  Bastelschritte, keine Workarounds für den Nutzer, kein „der Punkt geht aber nicht“. Jedes Modul muss
  vor der Auslieferung so weit wie möglich automatisch real getestet sein (CI: Pakete in Debian 13
  arm64, echte Dienste wie n8n im Container), nicht nur im Probelauf.
- Keine halb fertigen Sachen: vor jedem Push `pytest -q`, `ruff check .`, Shellcheck (läuft in CI);
  neue Module brauchen einen Probelauf-Test in `tests/test_install_dryrun.py`.
- Neue Funktionen von einer zweiten KI (Subagent) prüfen lassen und die Befunde umsetzen.
- Image wird per GitHub Actions gebaut (Workflow „Prüfen und Image bauen“, Ausgabe: ZIP für
  Raspberry Pi Imager). Erst melden, wenn der Build grün ist.
- `STAND.md` nach jeder größeren Änderung aktualisieren.
- Antworten an den Nutzer: Deutsch, „Meister“, kurz; Passwörter/Benutzernamen nie speichern.
- Bei Zeitangaben immer die aktuelle Uhrzeit (deutsche Zeit) dazuschreiben, z. B. „jetzt 08:42, fertig ca. 09:30“.
