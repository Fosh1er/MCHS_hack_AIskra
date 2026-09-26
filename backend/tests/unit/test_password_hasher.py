import pytest

from aiskra.modules.identity.infrastructure.security import ScryptPasswordHasher, SessionTokenIssuer


async def test_hash_and_verify() -> None:
    hasher = ScryptPasswordHasher(n=1024)
    h = await hasher.hash("Secret-2026")
    assert h.startswith("scrypt$1024$8$1$") and "Secret" not in h
    assert await hasher.verify("Secret-2026", h)
    assert not await hasher.verify("secret-2026", h)
    assert h != await hasher.hash("Secret-2026")  # соль


async def test_params_are_read_from_hash_and_malformed_is_rejected() -> None:
    old = await ScryptPasswordHasher(n=512).hash("Secret-2026")
    assert await ScryptPasswordHasher(n=1024).verify("Secret-2026", old)
    for bad in ["", "plain", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$a$b"]:
        assert not await ScryptPasswordHasher(n=1024).verify("Secret-2026", bad)
    await ScryptPasswordHasher(n=1024).burn("anything")


def test_bad_cost_parameter() -> None:
    with pytest.raises(ValueError):
        ScryptPasswordHasher(n=1000)


def test_tokens_are_random_and_stored_as_digest() -> None:
    tokens = SessionTokenIssuer()
    a, b = tokens.issue(), tokens.issue()
    assert a != b and len(a) >= 43
    assert tokens.digest(a) == tokens.digest(a) and len(tokens.digest(a)) == 64 and a not in tokens.digest(a)
