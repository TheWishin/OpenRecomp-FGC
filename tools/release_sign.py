"""Owner-only offline release signing. Never put private keys in the repository."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openrecomp import updater


def _encode(point):
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def public_key(seed):
    if len(seed) != 32:
        raise ValueError("A signing seed must be exactly 32 bytes.")
    hashed = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(bytes([hashed[0] & 248]) + hashed[1:31] + bytes([(hashed[31] & 63) | 64]), "little")
    base = updater._point(bytes.fromhex("58" + "66" * 31))
    return _encode(updater._mul(base, scalar))


def sign(seed, message):
    public = public_key(seed)
    hashed = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(bytes([hashed[0] & 248]) + hashed[1:31] + bytes([(hashed[31] & 63) | 64]), "little")
    nonce = int.from_bytes(hashlib.sha512(hashed[32:] + message).digest(), "little") % updater._L
    base = updater._point(bytes.fromhex("58" + "66" * 31))
    encoded = _encode(updater._mul(base, nonce))
    challenge = int.from_bytes(hashlib.sha512(encoded + public + message).digest(), "little") % updater._L
    return encoded + ((nonce + challenge * scalar) % updater._L).to_bytes(32, "little")


def _outside_repository(path):
    resolved = Path(path).resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("Private keys must stay outside the repository.")
    return resolved


def _seed(path):
    raw = _outside_repository(path).read_text(encoding="ascii").strip()
    try:
        value = bytes.fromhex(raw)
    except ValueError:
        raise ValueError("The signing key must contain one 64-digit hexadecimal seed.") from None
    if len(value) != 32:
        raise ValueError("The signing key must contain one 64-digit hexadecimal seed.")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("keygen")
    generate.add_argument("--out", required=True)
    public = commands.add_parser("public-key")
    public.add_argument("--key-file", required=True)
    signing = commands.add_parser("sign")
    signing.add_argument("--key-file", required=True)
    signing.add_argument("--channel", required=True)
    signing.add_argument("--version", required=True)
    signing.add_argument("--sums", required=True)
    signing.add_argument("--out", required=True)
    game = commands.add_parser("sign-t4", help="sign a Tekken 4 release's SHA256SUMS (game_releases SOURCES['t4'])")
    game.add_argument("--key-file", required=True)
    game.add_argument("--version", required=True, help="the release tag without its leading v, e.g. 0.1.0")
    game.add_argument("--sums", required=True)
    game.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "keygen":
        destination = _outside_repository(args.out)
        seed = os.urandom(32)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as output:
            output.write(seed.hex() + "\n")
    else:
        seed = _seed(args.key_file)
    public = public_key(seed)
    key_id = hashlib.sha256(public).hexdigest()[:16]
    if args.command == "sign":
        if not updater.version_key(args.version) or not updater._CHANNEL.fullmatch(args.channel):
            raise ValueError("A plain vX.Y.Z version and a unique channel name are required.")
        sums = Path(args.sums).read_bytes()
        if len(sums) > 65536:
            raise ValueError("SHA256SUMS is too large.")
        signature = sign(seed, updater.signature_message(args.channel, args.version, sums))
        if not updater.verify_ed25519(public, updater.signature_message(args.channel, args.version, sums), signature):
            raise ValueError("The generated signature failed verification.")
        metadata = dict(algorithm="ed25519", channel=args.channel, version=args.version, key_id=key_id, signature=signature.hex())
        with open(args.out, "x", encoding="ascii") as output:
            json.dump(metadata, output, indent=2)
            output.write("\n")
    elif args.command == "sign-t4":
        sums = Path(args.sums).read_bytes()
        if len(sums) > 65536:
            raise ValueError("SHA256SUMS is too large.")
        envelope = game_signature("t4", args.version, sums, seed)
        with open(args.out, "xb") as output:
            output.write(envelope)
    print(f"public key: {public.hex()}\nkey id: {key_id}")
    return 0


def game_signature(game, version, sums, seed):
    """SHA256SUMS.sig for a game release in the form game_releases.check_signature reads (T5DR's own releases
    are signed by T5DR's tools; this is for T4). Verified with the launcher's own check before it is returned."""
    from openrecomp import game_releases
    src = game_releases.SOURCES[game]
    if game_releases.version_key(version) is None or version[:1] in ("v", "V"):
        raise ValueError("The version is the tag without its leading v, e.g. 0.1.0 or 0.1.0-beta.1.")
    public = public_key(seed)
    statement = (f"{src.statement}\nversion={version}\nsums-sha256={hashlib.sha256(sums).hexdigest()}\n").encode("utf-8")
    envelope = (json.dumps(dict(format=src.sig_format, version=version, key=hashlib.sha256(public).hexdigest()[:16],
                                signature=sign(seed, statement).hex()), indent=2) + "\n").encode("ascii")
    game_releases.check_signature(src, version, sums, envelope, keys=(public.hex(),))
    return envelope


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        # Never print a key file's contents, a private seed or a traceback.
        print("Signing failed: " + (str(error) if isinstance(error, ValueError) else "cannot access the requested file"), file=sys.stderr)
        sys.exit(1)
