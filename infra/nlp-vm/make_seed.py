#!/usr/bin/env python3
"""VM15 用の非公開作業ディレクトリに VFAT seed を作り、読み戻して照合する。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import jsonschema
import yaml


class UniqueKeys(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate YAML key")
        return super().construct_mapping(node, deep)


def parse(data):
    try:
        return yaml.load(data, Loader=UniqueKeys)
    except (ValueError, yaml.YAMLError):
        raise SystemExit("invalid or duplicate YAML key") from None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("schema", "password_file", "public_key", "new_private_directory"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    schema = args.schema.read_bytes()
    if digest(schema) != "0e022b0dd2232868eab0039c8efa5b19d6f7c5ce2a751c7936080dde6cba95d4":
        raise SystemExit("expected Canonical 24.04.5 autoinstall schema")
    validator = jsonschema.validators.validator_for(json.loads(schema))(json.loads(schema))
    password = args.password_file.read_bytes().rstrip(b"\r\n")
    if not password or any(char in password for char in (b"\x00", b"\r", b"\n")):
        raise SystemExit("invalid single-line password file")
    crypt = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=password + b"\n",
                           capture_output=True, check=True).stdout.decode("ascii").strip()
    if not re.fullmatch(r"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", crypt):
        raise SystemExit("invalid crypt result")
    subprocess.run(["ssh-keygen", "-lf", args.public_key], stdout=subprocess.DEVNULL, check=True)
    key_fields = args.public_key.read_text().strip().split()
    key = " ".join(key_fields[:2])
    if not re.fullmatch(r"(ssh-rsa|ssh-ed25519|ecdsa-sha2-nistp(?:256|384|521)) [A-Za-z0-9+/]+=*", key):
        raise SystemExit("invalid public key")

    source = Path(__file__).resolve().parent / "autoinstall"
    template = (source / "user-data.tpl").read_text()
    parse(template)
    if template.count("{{PASSWORD_HASH}}") != 1 or template.count("{{SSH_PUBLIC_KEY}}") != 1:
        raise SystemExit("check template substitutions")
    rendered = template.replace("{{PASSWORD_HASH}}", crypt).replace("{{SSH_PUBLIC_KEY}}", key)
    meta = (source / "meta-data.tpl").read_bytes()
    config = parse(rendered)
    metadata = parse(meta)
    if (not rendered.startswith("#cloud-config\n") or set(config) != {"autoinstall"}
            or "{{" in rendered or b"{{" in meta or metadata.get("local-hostname") != "keiba-nlp"
            or not metadata.get("instance-id")):
        raise SystemExit("check NoCloud wrapper, metadata or placeholders")
    ai = config["autoinstall"]
    error = next(validator.iter_errors(ai), None)
    if error is not None:
        raise SystemExit("schema error at " + "/".join(map(str, error.absolute_path)))
    if (ai["identity"] != {"hostname": "keiba-nlp", "username": "nlp", "password": crypt}
            or ai["ssh"] != {"install-server": True, "authorized-keys": [key], "allow-pw": False}
            or ai["storage"] != {"layout": {"name": "lvm", "sizing-policy": "all",
                                            "match": {"id_path": "pci-0000:00:10.0-scsi-0:0:0:0"}}}
            or "user-data" in ai or "users" in ai):
        raise SystemExit("unexpected identity, SSH or disk selection")

    output = args.new_private_directory
    output.mkdir(mode=0o700, exist_ok=False)
    image = output / "cidata.img"
    with image.open("xb") as fp:
        fp.truncate(8 * 1024 * 1024)
    subprocess.run(["mkfs.vfat", "-n", "CIDATA", image], check=True, stdout=subprocess.DEVNULL)
    for name, data in (("user-data", rendered.encode("utf-8")), ("meta-data", meta)):
        path = output / name
        path.write_bytes(data)
        subprocess.run(["mcopy", "-i", image, path, "::" + name], check=True)
        restored = subprocess.check_output(["mtype", "-i", image, "::" + name])
        if restored != data:
            raise SystemExit("VFAT read-back failed: " + name)
        print(name, len(data), digest(data))
    print("cidata.img", image.stat().st_size, digest(image.read_bytes()))


if __name__ == "__main__":
    main()
