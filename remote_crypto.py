"""
End-to-end encryption for "control from anywhere".

AES-256-GCM (the same standard browsers and https use) through the OpenSSL
library that already ships with Python (libcrypto, used by Python's own `ssl`
module), called with ctypes. Keys are derived with HKDF-SHA256 (standard
library hmac). The phone page uses the browser's built-in WebCrypto with the
same algorithms, so what one side locks, only the other side can open.

Message format: 12-byte random nonce || ciphertext || 16-byte tag.
"""

import base64
import ctypes
import ctypes.util
import glob
import hashlib
import hmac
import os
import secrets
import ssl  # loads OpenSSL into the process, so we can find it below
import sys

NONCE_SIZE = 12
TAG_SIZE = 16
KEY_SIZE = 32

EVP_CTRL_GCM_SET_IVLEN = 0x9
EVP_CTRL_GCM_GET_TAG = 0x10
EVP_CTRL_GCM_SET_TAG = 0x11


class CryptoError(Exception):
    """Something could not be locked or opened (wrong key, changed data, no OpenSSL)."""


def _load_libcrypto():
    names = []
    if os.name == "nt":
        # Python 3.11+ ships libcrypto-3.dll, 3.7–3.10 libcrypto-1_1.dll (next to python.exe,
        # or in the DLLs folder). Because `ssl` is imported above, it is usually already loaded.
        folders = [os.path.dirname(sys.executable), os.path.join(sys.base_prefix, "DLLs"), sys.base_prefix]
        for base in ("libcrypto-3-x64", "libcrypto-3", "libcrypto-1_1-x64", "libcrypto-1_1"):
            names.append(base)
            names += [os.path.join(f, base + ".dll") for f in folders]
        for folder in folders:
            names += sorted(glob.glob(os.path.join(folder, "libcrypto*.dll")))
    else:
        found = ctypes.util.find_library("crypto")
        names += [n for n in (found, "libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.dylib") if n]
    for name in names:
        try:
            library = ctypes.CDLL(name)
            library.EVP_aes_256_gcm  # check that it is really libcrypto
            return library
        except (OSError, AttributeError):
            continue
    return None


_lib = _load_libcrypto()
if _lib is not None:
    _VP = ctypes.c_void_p
    _BUF = ctypes.c_char_p
    _INTP = ctypes.POINTER(ctypes.c_int)
    for _name, _args, _res in [
        ("EVP_CIPHER_CTX_new", (), _VP),
        ("EVP_CIPHER_CTX_free", (_VP,), None),
        ("EVP_aes_256_gcm", (), _VP),
        ("EVP_EncryptInit_ex", (_VP, _VP, _VP, _BUF, _BUF), ctypes.c_int),
        ("EVP_DecryptInit_ex", (_VP, _VP, _VP, _BUF, _BUF), ctypes.c_int),
        ("EVP_EncryptUpdate", (_VP, _VP, _INTP, _BUF, ctypes.c_int), ctypes.c_int),
        ("EVP_DecryptUpdate", (_VP, _VP, _INTP, _BUF, ctypes.c_int), ctypes.c_int),
        ("EVP_EncryptFinal_ex", (_VP, _VP, _INTP), ctypes.c_int),
        ("EVP_DecryptFinal_ex", (_VP, _VP, _INTP), ctypes.c_int),
        ("EVP_CIPHER_CTX_ctrl", (_VP, ctypes.c_int, ctypes.c_int, _VP), ctypes.c_int),
    ]:
        _function = getattr(_lib, _name)
        _function.argtypes = _args
        _function.restype = _res


def available():
    """True if AES-GCM can be used on this computer."""
    return _lib is not None


def _check(result, what):
    if result != 1:
        raise CryptoError(f"OpenSSL {what} failed")


def encrypt(key, plaintext, aad=b"", nonce=None):
    """Lock data with AES-256-GCM. Returns nonce || ciphertext || tag."""
    if _lib is None:
        raise CryptoError("OpenSSL (libcrypto) was not found, so encryption is not available.")
    if len(key) != KEY_SIZE:
        raise CryptoError("the key must be 32 bytes")
    nonce = nonce or secrets.token_bytes(NONCE_SIZE)
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise CryptoError("OpenSSL could not start")
    try:
        _check(_lib.EVP_EncryptInit_ex(ctx, _lib.EVP_aes_256_gcm(), None, None, None), "init")
        _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, len(nonce), None), "nonce length")
        _check(_lib.EVP_EncryptInit_ex(ctx, None, None, key, nonce), "key")
        length = ctypes.c_int(0)
        if aad:
            _check(_lib.EVP_EncryptUpdate(ctx, None, ctypes.byref(length), aad, len(aad)), "aad")
        out = ctypes.create_string_buffer(len(plaintext) + 16)
        _check(_lib.EVP_EncryptUpdate(ctx, out, ctypes.byref(length), plaintext, len(plaintext)), "encrypt")
        written = length.value
        final = ctypes.create_string_buffer(16)
        _check(_lib.EVP_EncryptFinal_ex(ctx, final, ctypes.byref(length)), "final")
        tag = ctypes.create_string_buffer(TAG_SIZE)
        _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, TAG_SIZE, tag), "tag")
        return nonce + out.raw[:written] + final.raw[:length.value] + tag.raw
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def decrypt(key, message, aad=b""):
    """Open data locked by encrypt() (or by the browser). Raises CryptoError if anything was changed."""
    if _lib is None:
        raise CryptoError("OpenSSL (libcrypto) was not found, so encryption is not available.")
    if len(key) != KEY_SIZE or len(message) < NONCE_SIZE + TAG_SIZE:
        raise CryptoError("message cannot be opened")
    nonce, body, tag = message[:NONCE_SIZE], message[NONCE_SIZE:-TAG_SIZE], message[-TAG_SIZE:]
    ctx = _lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise CryptoError("OpenSSL could not start")
    try:
        _check(_lib.EVP_DecryptInit_ex(ctx, _lib.EVP_aes_256_gcm(), None, None, None), "init")
        _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, NONCE_SIZE, None), "nonce length")
        _check(_lib.EVP_DecryptInit_ex(ctx, None, None, key, nonce), "key")
        length = ctypes.c_int(0)
        if aad:
            _check(_lib.EVP_DecryptUpdate(ctx, None, ctypes.byref(length), aad, len(aad)), "aad")
        out = ctypes.create_string_buffer(len(body) + 16)
        _check(_lib.EVP_DecryptUpdate(ctx, out, ctypes.byref(length), body, len(body)), "decrypt")
        written = length.value
        tag_buffer = ctypes.create_string_buffer(tag, TAG_SIZE)
        _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, TAG_SIZE, tag_buffer), "tag")
        final = ctypes.create_string_buffer(16)
        if _lib.EVP_DecryptFinal_ex(ctx, final, ctypes.byref(length)) <= 0:
            raise CryptoError("message cannot be opened (wrong key or changed on the way)")
        return out.raw[:written] + final.raw[:length.value]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def hkdf(secret, info, length=KEY_SIZE, salt=b""):
    """HKDF-SHA256 (RFC 5869): turn one secret into separate keys for separate purposes."""
    prk = hmac.new(salt or b"\x00" * 32, secret, hashlib.sha256).digest()
    output, block, counter = b"", b"", 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def b64(data):
    """base64url without padding (safe in links)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(text):
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_key():
    return secrets.token_bytes(KEY_SIZE)


# ---------------------------------------------------------------------------
# ECDH P-256 (for invitations): the invitation link carries only the PUBLIC key of
# the phone, so a copy of the e-mail is useless to anyone else. The laptop makes a
# one-time key pair, derives a shared secret with the phone's public key, and locks
# the access keys with it; only the phone (with its private key) can open them.
# Keys are exchanged as DER "SubjectPublicKeyInfo", the format WebCrypto calls "spki".
# ---------------------------------------------------------------------------

NID_X9_62_prime256v1 = 415
EVP_PKEY_EC = 408

if _lib is not None:
    _PP = ctypes.POINTER(ctypes.c_void_p)
    for _name, _args, _res in [
        ("EC_KEY_new_by_curve_name", (ctypes.c_int,), _VP),
        ("EC_KEY_generate_key", (_VP,), ctypes.c_int),
        ("EC_KEY_free", (_VP,), None),
        ("EVP_PKEY_new", (), _VP),
        ("EVP_PKEY_assign", (_VP, ctypes.c_int, _VP), ctypes.c_int),
        ("EVP_PKEY_free", (_VP,), None),
        ("i2d_PUBKEY", (_VP, _PP), ctypes.c_int),
        ("d2i_PUBKEY", (_VP, _PP, ctypes.c_long), _VP),
        ("EVP_PKEY_CTX_new", (_VP, _VP), _VP),
        ("EVP_PKEY_CTX_free", (_VP,), None),
        ("EVP_PKEY_derive_init", (_VP,), ctypes.c_int),
        ("EVP_PKEY_derive_set_peer", (_VP, _VP), ctypes.c_int),
        ("EVP_PKEY_derive", (_VP, _VP, ctypes.POINTER(ctypes.c_size_t)), ctypes.c_int),
    ]:
        _function = getattr(_lib, _name)
        _function.argtypes = _args
        _function.restype = _res


def _public_der(pkey):
    size = _lib.i2d_PUBKEY(pkey, None)
    if size <= 0:
        raise CryptoError("cannot export the public key")
    buffer = ctypes.create_string_buffer(size)
    pointer = ctypes.c_void_p(ctypes.addressof(buffer))
    _lib.i2d_PUBKEY(pkey, ctypes.byref(pointer))
    return buffer.raw


def ecdh_shared_secret(peer_public_der):
    """
    Make a one-time P-256 key pair and agree on a secret with the peer's public key.
    Returns (our public key as DER, 32-byte shared secret).
    """
    if _lib is None:
        raise CryptoError("OpenSSL (libcrypto) was not found, so encryption is not available.")
    ec_key = _lib.EC_KEY_new_by_curve_name(NID_X9_62_prime256v1)
    pkey = _lib.EVP_PKEY_new()
    peer = ctx = None
    try:
        if not ec_key or not pkey or _lib.EC_KEY_generate_key(ec_key) != 1:
            raise CryptoError("cannot make a key pair")
        if _lib.EVP_PKEY_assign(pkey, EVP_PKEY_EC, ec_key) != 1:
            raise CryptoError("cannot make a key pair")
        ec_key = None  # now owned by pkey
        data = ctypes.create_string_buffer(peer_public_der, len(peer_public_der))
        pointer = ctypes.c_void_p(ctypes.addressof(data))
        peer = _lib.d2i_PUBKEY(None, ctypes.byref(pointer), len(peer_public_der))
        if not peer:
            raise CryptoError("the public key in the invitation is not valid")
        ctx = _lib.EVP_PKEY_CTX_new(pkey, None)
        if not ctx or _lib.EVP_PKEY_derive_init(ctx) != 1 or _lib.EVP_PKEY_derive_set_peer(ctx, peer) != 1:
            raise CryptoError("the public key in the invitation cannot be used")
        size = ctypes.c_size_t(0)
        if _lib.EVP_PKEY_derive(ctx, None, ctypes.byref(size)) != 1:
            raise CryptoError("key agreement failed")
        secret = ctypes.create_string_buffer(size.value)
        if _lib.EVP_PKEY_derive(ctx, secret, ctypes.byref(size)) != 1:
            raise CryptoError("key agreement failed")
        return _public_der(pkey), secret.raw[:size.value]
    finally:
        if ctx:
            _lib.EVP_PKEY_CTX_free(ctx)
        if peer:
            _lib.EVP_PKEY_free(peer)
        if pkey:
            _lib.EVP_PKEY_free(pkey)
        if ec_key:
            _lib.EC_KEY_free(ec_key)
