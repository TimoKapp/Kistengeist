#!/usr/bin/env python3
"""Echter Gegentest der DynDNS-Anbieter (CI): mit absichtlich falschen Zugangsdaten muss jeder Anbieter
„Zugang abgelehnt“ melden – so prüfen wir Adresse, Parameter, Anmeldung und Antwort-Auswertung,
ohne ein echtes Konto zu brauchen. Dazu: eigene öffentliche IPv4 ermitteln."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stage-claude", "00-install",
                                "files", "rootfs", "opt", "kistengeist", "lib"))
import kistengeist_ddns as ddns  # noqa: E402

CASES = [
    ("ipv64", "kistengeist-ci-test.ipv64.net", {"token": "ciFalscherToken0000000000"}),
    ("dynv6", "kistengeist-ci-test.dynv6.net", {"token": "ciFalscherToken0000000000"}),
    ("noip", "kistengeist-ci-test.ddns.net", {"user": "kistengeist-ci-falsch", "password": "falsch-ci-0000"}),
    ("duckdns", "kistengeist-ci-test.duckdns.org", {"token": "00000000-0000-0000-0000-000000000000"}),
]
fail = 0
ip = ddns.public_ipv4()
print(f"öffentliche IPv4: {ip}")
if not ip:
    print("::error::öffentliche IPv4 nicht ermittelbar")
    fail = 1
for provider, host, secret in CASES:
    url, headers = ddns.build_request(provider, host, secret, ip, None)
    try:
        status, body = ddns.http_get(url, headers)
    except OSError as exc:
        print(f"::error::{provider} nicht erreichbar: {exc}")
        fail = 1
        continue
    result, message = ddns.parse_response(provider, status, body)
    print(f"{provider}: HTTP {status} {body.strip()[:80]!r} -> {result} ({message})")
    if result != "fatal":
        print(f"::error::{provider}: falsche Zugangsdaten nicht als abgelehnt erkannt")
        fail = 1
sys.exit(fail)
