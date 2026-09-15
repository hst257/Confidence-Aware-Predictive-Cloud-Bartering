"""Stateless seeded randomness keyed by simulated minute and purpose."""

import hashlib
import math
import secrets


def random_seed() -> int:
    return secrets.randbelow(2_147_483_646) + 1


def uniform(seed: int, *parts: object) -> float:
    material = "|".join([str(seed), *(str(part) for part in parts)]).encode("utf-8")
    digest = hashlib.blake2b(material, digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64 - 1)


def normal(seed: int, *parts: object) -> float:
    first = max(uniform(seed, *parts, "normal-a"), 1e-12)
    second = uniform(seed, *parts, "normal-b")
    return math.sqrt(-2 * math.log(first)) * math.cos(2 * math.pi * second)


def choice(seed: int, values: list, *parts: object):
    return values[min(len(values) - 1, int(uniform(seed, *parts) * len(values)))]

