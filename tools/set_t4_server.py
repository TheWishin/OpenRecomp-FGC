r"""Fill in (or clear) the T4 lobby server the launcher ships with: openrecomp\vendor\servers.json.

    python tools\set_t4_server.py --host 46.224.146.6 --fingerprint <sha256 printed by the T4 server install>
    python tools\set_t4_server.py --clear          back to "no T4 lobby server is set up yet"
    python tools\set_t4_server.py --show

The file holds one entry, "T4 Online": TLS with the server's self-signed certificate pinned by its SHA-256
fingerprint, "shared_login" (the T4 server shares T5DR Online's accounts, so a T5DR login saved on the same host
may log in with one press) and "default". While host and fingerprint are empty the entry is a placeholder: the
launcher shows "no server" and offers Direct IP / VPN. OPENRECOMP_T4_SERVER and the launcher config's
t4_lobby_server still override it on one PC. Only edits that one file; never contacts the server.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys

PATH = Path(__file__).resolve().parents[1] / "openrecomp" / "vendor" / "servers.json"
FORMAT = "t5dr-servers/1"
NAME = "T4 Online"
HOST_RE = re.compile(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*")


def entry(host="", port=7791, fingerprint="", region="EU"):
    # UDP: the lobby's register/ping/relay port is the TCP port, the NAT probe the next one.
    return dict(name=NAME, host=host, port=port, tls="pin", fingerprint=fingerprint, udp_ports=[port, port + 1],
                region=region, shared_login=True, default=True)


def clean_fingerprint(text):
    fp = re.sub(r"[\s:]", "", str(text or "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", fp):
        raise ValueError("the fingerprint must be the certificate's SHA-256: 64 hex digits (colons allowed)")
    return fp


def clean_host(text):
    host = str(text or "").strip()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not HOST_RE.fullmatch(host) or host.replace(".", "").isdigit():
            raise ValueError("the host must be an IP address or a DNS name") from None
        return host.lower()
    if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_private:
        raise ValueError("the shipped server must be a public address")
    return str(address)


def write(doc, path=PATH):
    text = json.dumps(doc, indent=2) + "\n"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=7791)
    parser.add_argument("--fingerprint")
    parser.add_argument("--region", default="EU")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--file", default=str(PATH), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = Path(args.file)
    if args.show:
        print(path.read_text(encoding="utf-8"), end="")
        return 0
    if args.clear:
        write(dict(format=FORMAT, servers=[entry()]), path)
        print("T4 lobby server cleared (placeholder): the launcher shows 'no server'.")
        return 0
    if not args.host or not args.fingerprint:
        parser.error("give --host and --fingerprint, or --clear / --show")
    if not 1 <= args.port <= 65534:
        parser.error("--port must be 1..65534 (the NAT probe uses the next port)")
    try:
        host, fingerprint = clean_host(args.host), clean_fingerprint(args.fingerprint)
    except ValueError as error:
        parser.error(str(error))
    write(dict(format=FORMAT, servers=[entry(host, args.port, fingerprint, args.region[:32])]), path)
    print("T4 lobby server set: %s:%d#%s (shared T5DR login, default)" % (host, args.port, fingerprint))
    return 0


if __name__ == "__main__":
    sys.exit(main())
