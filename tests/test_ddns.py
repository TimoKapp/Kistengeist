"""DynDNS-Anbieter: Eingaben, Anfragen, Antworten und „nur bei Änderung melden“."""

import base64
import urllib.parse

import kistengeist_ddns as ddns
import pytest


def query(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query, keep_blank_values=True))


@pytest.mark.parametrize("provider,raw,host", [
    ("ipv64", "https://MeinPi.ipv64.net/", "meinpi.ipv64.net"),
    ("ipv64", "meinpi.home64.de", "meinpi.home64.de"),
    ("dynv6", "meinpi.dynv6.net", "meinpi.dynv6.net"),
    ("noip", "meinpi.hopto.org", "meinpi.hopto.org"),
    ("duckdns", "meinpi", "meinpi.duckdns.org"),
])
def test_normalize_host(provider, raw, host):
    assert ddns.normalize_host(provider, raw) == host


@pytest.mark.parametrize("provider,raw", [
    ("ipv64", "meinpi.example.com"), ("ipv64", "a.b.ipv64.net"), ("dynv6", "meinpi"),
    ("noip", "ddns.net"), ("duckdns", "mein pi"), ("desec", "x.dedyn.io"),
])
def test_normalize_host_rejects(provider, raw):
    with pytest.raises(ddns.DdnsError):
        ddns.normalize_host(provider, raw)


def test_normalize_secret():
    assert ddns.normalize_secret("noip", user=" u1 ", password="p:w#1") == {"user": "u1", "password": "p:w#1"}
    assert ddns.normalize_secret("duckdns", " A1B2C3D4-0000-1111-2222-333344445555") == \
        {"token": "a1b2c3d4-0000-1111-2222-333344445555"}
    for args in (("noip", "", "", "pw"), ("noip", "", "u", "a\nb"), ("ipv64", "kurz"), ("duckdns", "abc")):
        with pytest.raises(ddns.DdnsError):
            ddns.normalize_secret(*args)


def test_build_requests():
    url, h = ddns.build_request("ipv64", "a.ipv64.net", {"token": "T0k"}, "1.2.3.4", "2001:db8::1")
    assert url.startswith("https://ipv64.net/nic/update?") and h["Authorization"] == "Bearer T0k"
    assert query(url) == {"domain": "a.ipv64.net", "output": "min", "ip": "1.2.3.4", "ip6": "2001:db8::1"}
    url, _ = ddns.build_request("ipv64", "a.ipv64.net", {"token": "T"}, None, "2001:db8::1", v6only=True)
    assert url.startswith("https://ipv64.net/nic/update?") and "ip" not in query(url)

    url, _ = ddns.build_request("dynv6", "a.dynv6.net", {"token": "T"}, "1.2.3.4", None)
    assert url.startswith("https://ipv4.dynv6.com/api/update?")
    assert query(url) == {"zone": "a.dynv6.net", "token": "T", "ipv4": "1.2.3.4"}
    url, _ = ddns.build_request("dynv6", "a.dynv6.net", {"token": "T"}, None, "2001:db8::1", v6only=True)
    assert query(url)["ipv4"] == "-" and query(url)["ipv6"] == "2001:db8::1"

    url, h = ddns.build_request("noip", "a.ddns.net", {"user": "u", "password": "p:w"}, "1.2.3.4", "2001:db8::1")
    assert query(url) == {"hostname": "a.ddns.net", "myip": "1.2.3.4,2001:db8::1"}
    assert base64.b64decode(h["Authorization"].split()[1]).decode() == "u:p:w"
    assert "@" in h["User-Agent"]  # No-IP verlangt Kontaktangabe im User-Agent

    url, _ = ddns.build_request("duckdns", "a.duckdns.org", {"token": "T"}, None, None)
    assert query(url) == {"domains": "a", "token": "T", "verbose": "true", "ip": ""}
    url, _ = ddns.build_request("duckdns", "a.duckdns.org", {"token": "T"}, None, "2001:db8::1")
    assert "ipv6" not in query(url)                      # sonst schaltet DuckDNS die IPv4-Erkennung ab
    url, _ = ddns.build_request("duckdns", "a.duckdns.org", {"token": "T"}, None, None, True, clear=True)
    assert query(url)["clear"] == "true"


@pytest.mark.parametrize("provider,status,body,result", [
    ("ipv64", 200, "good", "ok"), ("ipv64", 200, "nochg", "ok"), ("ipv64", 401, "badauth", "fatal"),
    ("ipv64", 429, "Updateintervall overcommited", "retry"), ("ipv64", 400, "fail", "fatal"),
    ("ipv64", 500, "", "retry"),
    ("dynv6", 200, "addresses updated", "ok"), ("dynv6", 401, "invalid authentication token", "fatal"),
    ("noip", 200, "good 1.2.3.4", "ok"), ("noip", 200, "nochg 1.2.3.4", "ok"), ("noip", 200, "nohost", "fatal"),
    ("noip", 200, "abuse", "fatal"), ("noip", 200, "911", "retry"),
    ("duckdns", 200, "OK\n1.2.3.4\n\nUPDATED", "ok"), ("duckdns", 200, "KO", "fatal"),
])
def test_parse_response(provider, status, body, result):
    assert ddns.parse_response(provider, status, body)[0] == result


class FakeGet:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, headers, timeout=20):
        self.calls.append(url)
        return self.answers.pop(0)


def test_only_on_change_and_daily():
    secret = {"token": "T0kenTok"}
    get = FakeGet([(200, "good")] * 3)
    kw = {"get": get, "detect": False, "ipv4": "1.2.3.4", "ipv6": None}
    state, res, _ = ddns.run_update("ipv64", "a.ipv64.net", secret, False, {}, now=1000, **kw)
    assert res == "ok" and len(get.calls) == 1
    state, res, _ = ddns.run_update("ipv64", "a.ipv64.net", secret, False, state, now=1300, **kw)
    assert res == "skip" and len(get.calls) == 1            # gleiche IP: nichts senden (Tageslimit)
    state, res, _ = ddns.run_update("ipv64", "a.ipv64.net", secret, False, state, now=1600,
                                    **{**kw, "ipv4": "5.6.7.8"})
    assert res == "ok" and len(get.calls) == 2              # neue IP: sofort melden
    state, res, _ = ddns.run_update("ipv64", "a.ipv64.net", secret, False, state, now=1600 + 25 * 3600,
                                    **{**kw, "ipv4": "5.6.7.8"})
    assert res == "ok" and len(get.calls) == 3              # einmal täglich trotzdem


def test_fatal_blocks_until_credentials_change():
    get = FakeGet([(200, "badauth"), (200, "good 1.2.3.4")])
    kw = {"get": get, "detect": False, "ipv4": "1.2.3.4", "ipv6": None}
    old = {"user": "u", "password": "alt"}
    state, res, _ = ddns.run_update("noip", "a.ddns.net", old, False, {}, now=0, **kw)
    assert res == "fatal"
    state, res, _ = ddns.run_update("noip", "a.ddns.net", old, False, state, now=4000, **kw)
    assert res == "blocked" and len(get.calls) == 1         # No-IP: nach Fehler nicht weiter anfragen
    state, res, _ = ddns.run_update("noip", "a.ddns.net", {"user": "u", "password": "neu"}, False, state,
                                    now=4100, **kw)
    assert res == "ok" and len(get.calls) == 2


def test_retry_pause_and_v6only():
    get = FakeGet([(200, "911"), (200, "OK"), (200, "OK\n\n2001:db8::1\nUPDATED")])
    kw = {"get": get, "detect": False, "ipv4": "1.2.3.4", "ipv6": None}
    state, res, _ = ddns.run_update("noip", "a.ddns.net", {"user": "u", "password": "p"}, False, {}, now=0, **kw)
    assert res == "retry"
    assert ddns.run_update("noip", "a.ddns.net", {"user": "u", "password": "p"}, False, state, now=600,
                           **kw)[1] == "skip"
    # DuckDNS + DS-Lite: einmal alte IPv4 löschen, dann nur IPv6
    state, res, _ = ddns.run_update("duckdns", "a.duckdns.org", {"token": "T"}, True, {}, now=0, get=get,
                                    detect=False, ipv4=None, ipv6="2001:db8::1")
    assert res == "ok" and state["cleared"] and "clear=true" in get.calls[1] and "ipv6=2001" in get.calls[2]
    assert ddns.run_update("dynv6", "a.dynv6.net", {"token": "T"}, True, {}, get=get, detect=False,
                           ipv4=None, ipv6=None)[1] == "retry"


def test_local_ipv6_skips_docker_and_ula():
    out = ("3: docker0    inet6 2001:db8:1::1/64 scope global\n"
           "2: wlan0    inet6 fd00::5/64 scope global dynamic\n"
           "2: wlan0    inet6 2a02:810d::42/64 scope global dynamic mngtmpaddr\n")
    assert ddns.local_ipv6(out) == "2a02:810d::42"


def test_public_ipv4_validates():
    assert ddns.public_ipv4(FakeGet([(200, "<html>"), (200, "93.184.216.34\n")])) == "93.184.216.34"
    assert ddns.public_ipv4(FakeGet([(200, "10.0.0.1"), (500, "")])) is None


def test_v6only_skips_unchanged():
    get = FakeGet([(200, "good")] * 3)
    kw = {"get": get, "detect": False, "ipv4": None, "ipv6": "2a02:810d::42"}
    state = {}
    for i in range(5):                                      # DS-Lite: nicht alle 5 Minuten melden
        state, _res, _ = ddns.run_update("ipv64", "a.ipv64.net", {"token": "T0kenTok"}, True, state,
                                         now=1000 + i * 300, **kw)
    assert len(get.calls) == 1


def test_unknown_ipv4_blind_update_rate():
    get = FakeGet([(200, "nochg")] * 5)
    kw = {"get": get, "detect": False, "ipv4": None, "ipv6": None}
    secret = {"user": "u", "password": "p"}
    state = {}
    for i in range(10):                                     # 10 Stunden ohne eigene IPv4
        state, _res, _ = ddns.run_update("noip", "a.ddns.net", secret, False, state, now=i * 3600, **kw)
    assert len(get.calls) == 1                              # No-IP: höchstens alle 12 Stunden blind
