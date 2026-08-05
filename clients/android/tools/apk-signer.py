#!/usr/bin/env python3
"""Print the signer certificate fingerprint of an APK.

Android decides whether one APK may replace another by comparing exactly this
certificate. If it differs, the install is refused, and the only way forward is
to uninstall first — which wipes the app's data, including the paired device
token. The next launch then asks for a pairing code again.

That is not hypothetical. The first CI-built APK was signed with a key the
runner generated eight seconds earlier, because no keystore existed. Every build
produced a different key, so every install was an uninstall, and every install
meant pairing again. Nothing reported it: the APK was valid, signed, and
installable — just never *the same app* as the one before it.

So the fingerprint gets printed on every build and compared against the last
one. A key that changed by accident is now something you can see.

    python3 apk-signer.py <apk>            print the fingerprint
    python3 apk-signer.py <apk> <expected> exit 1 if it does not match
"""
import hashlib, struct, sys

data = open(sys.argv[1], "rb").read()

# End of central directory -> offset of central directory.
eocd = data.rfind(b"PK\x05\x06")
cd_offset = struct.unpack_from("<I", data, eocd + 16)[0]

# The APK Signing Block sits immediately before the central directory.
magic_at = cd_offset - 16
assert data[magic_at:magic_at + 16] == b"APK Sig Block 42", "no APK signing block"
size_at = magic_at - 8
block_size = struct.unpack_from("<Q", data, size_at)[0]
block_start = cd_offset - block_size - 8

# Walk the id-value pairs.
pos = block_start + 8
end = size_at
found = {}
while pos < end:
    pair_len = struct.unpack_from("<Q", data, pos)[0]
    pair_id = struct.unpack_from("<I", data, pos + 8)[0]
    found[pair_id] = (pos + 12, pair_len - 4)
    pos += 8 + pair_len

SCHEMES = {0x7109871A: "v2", 0xF05368C0: "v3"}
fingerprints: dict[str, str] = {}
for scheme_id, name in SCHEMES.items():
    if scheme_id not in found:
        continue
    off, _ = found[scheme_id]

    def seq(at):
        """Read a uint32-length-prefixed blob, return (payload_offset, length)."""
        return at + 4, struct.unpack_from("<I", data, at)[0]

    signers_at, _ = seq(off)          # signers sequence
    signer_at, _ = seq(signers_at)    # first signer
    signed_at, _ = seq(signer_at)     # signed data
    digests_at, digests_len = seq(signed_at)
    certs_at, _ = seq(digests_at + digests_len)   # certificates sequence
    cert_at, cert_len = seq(certs_at)             # first certificate (DER)

    der = data[cert_at:cert_at + cert_len]
    digest = hashlib.sha256(der).hexdigest()
    fingerprints[name] = digest
    print(f"  {name}  signer cert SHA-256: {digest}")

if not fingerprints:
    sys.exit("no v2 or v3 signature found; this APK is not signed the way Android expects")

if len(sys.argv) > 2:
    expected = sys.argv[2].strip().lower()
    actual = next(iter(fingerprints.values()))
    if actual != expected:
        sys.exit(
            f"\nSIGNING KEY CHANGED\n"
            f"  expected {expected}\n"
            f"  actual   {actual}\n\n"
            "Android will refuse to install this over the previous build. Installing\n"
            "it means uninstalling first, which wipes the record held on the device\n"
            "and the paired token, so the app will ask for a pairing code again.\n")
    print("  matches the expected signing key")
