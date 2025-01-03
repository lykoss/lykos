from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
import os
import random as py_random
from typing import Optional

__all__ = ["random", "seed_function", "get_seed"]
# seed_function must be a function accepting an int and returning a bytestring containing that many random bytes
seed_function = os.urandom

# internal constants
KEY_SIZE = 32
NONCE_SIZE = 16
BUFFER_SIZE = 1024

def get_seed():
    """Retrieve a seed suitable for passing to random.seed()."""
    return seed_function(KEY_SIZE)

class GameRNG(py_random.Random):
    """A better RNG than default random while providing the same API.

    This RNG makes use of chacha20 to provide a bitstream, with support
    for deterministic keying for replays. An extensibility point is provided
    via random.SEED_FUNCTION, which can be set to an arbitrary callback in
    custom hooks.py to override default seeding behavior (os.urandom).

    This is not secure for any sort of cryptographic use; it is purely to
    provide a better RNG for gameplay purposes.
    """
    def __init__(self, seed=None):
        self._cur: bytes = b""
        self._next: bytes = b""
        self._buffer: bytes = b""
        self._offset: int = 0
        super().__init__(seed)

    def getstate(self):
        return self._cur, self._offset

    def setstate(self, state):
        key, offset, reseed_count = state
        if not isinstance(key, bytes) or len(key) != KEY_SIZE:
            raise TypeError("Invalid key state")
        if not isinstance(offset, int) or offset < KEY_SIZE or offset >= BUFFER_SIZE:
            raise TypeError("Invalid offset state")

        cipher = Cipher(algorithms.ChaCha20(key, b"\x00" * NONCE_SIZE), None)
        enc = cipher.encryptor()
        self._cur = key
        self._buffer = enc.update(b"\x00" * BUFFER_SIZE)
        self._next = self._buffer[0:KEY_SIZE]
        self._offset = offset

    def seed(self, a: Optional[bytes] = None, version: int = 2) -> None:
        if a is None:
            self._cur = self._next = seed_function(KEY_SIZE)
        elif not isinstance(a, bytes):
            raise TypeError(f"seed must be a bytes string, got {type(a)} instead")
        elif len(a) != KEY_SIZE:
            raise TypeError(f"seed must be {KEY_SIZE} bytes, got {len(a)} bytes instead")
        else:
            self._cur = self._next = a

        self._reseed()

    def getrandbits(self, k: int, /) -> int:
        # implementation details largely lifted from SystemRandom.getrandbits
        # and updated to use self.randbytes instead of urandom
        if k < 0:
            raise ValueError("Number of bits must be non-negative")

        numbytes = (k + 7) // 8  # bits / 8 and rounded up
        x = int.from_bytes(self.randbytes(numbytes))
        return x >> (numbytes * 8 - k)  # trim excess bits

    def random(self) -> float:
        # implementation details largely lifted from SystemRandom.random
        # and updated to use self.randbytes instead of urandom
        # python floats are doubles, and doubles have 53 bits for the significand
        # we don't want to populate exponent with any random data or else we massively bias results
        return (int.from_bytes(self.randbytes(7)) >> 3) * (2 ** -53)

    def randbytes(self, n) -> bytes:
        if n < 0:
            raise ValueError("Number of bytes must be non-negative")
        elif n == 0:
            return b""

        buf = bytearray(n)
        i = 0
        while n > 0:
            remaining = BUFFER_SIZE - self._offset
            if remaining > n:
                buf[i:i + n] = self._buffer[self._offset:self._offset + n]
                self._offset += n
                break
            else:
                buf[i:i + remaining] = self._buffer[self._offset:]
                n -= remaining
                i += remaining
                self._reseed()

        return bytes(buf)

    def _reseed(self) -> None:
        cipher = Cipher(algorithms.ChaCha20(self._next, b"\x00" * NONCE_SIZE), None)
        enc = cipher.encryptor()
        self._cur = self._next
        self._buffer = enc.update(b"\x00" * BUFFER_SIZE)
        self._next = self._buffer[0:KEY_SIZE]
        self._offset = KEY_SIZE

# named so things can do `from src.random import random` and use all of the `random.blah()` APIs without change
random = GameRNG()
