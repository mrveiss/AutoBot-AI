# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Secret-shaped file names, and the near misses that are not (#19339)."""

import pytest

from autobot_shared.secret_file_names import is_secret_file_name


@pytest.mark.parametrize(
    "name",
    [
        "credentials.json", "secrets.toml", "api-token.txt", "db_password.conf", "my.private.key.txt",
        "server.pem", "tls.key", "id_rsa", "id_ed25519.pub", ".env", ".env.local", "prod.env",
        ".netrc", "API_KEY.yaml", "apikeys.json", "service-account-key.json", "key.json", "keys.json",
        "ssh_key", "gcp.service_account.key.json",
    ],
)  # fmt: skip
def test_a_secret_shaped_name_is_matched(name: str) -> None:
    assert is_secret_file_name(name)


@pytest.mark.parametrize(
    "name",
    ["tokenizer.py", "secretary.md", "README.md", "app.conf", "keyboard.md", "guide.md", "key-concepts.md", "key.md"],
)
def test_an_ordinary_name_is_not(name: str) -> None:
    assert not is_secret_file_name(name)


_OLD_WORDS = [
    "secret", "secrets", "credential", "credentials", "token", "tokens", "password", "passwords", "passwd",
    "apikey", "apikeys", "privatekey",
]  # fmt: skip


@pytest.mark.parametrize("word", _OLD_WORDS)
@pytest.mark.parametrize("shape", ["{w}.txt", "x_{w}.txt", "{w}_x.txt", "{W}.TXT", "x-{W}.md"])
def test_every_word_of_the_old_list_still_marks_a_file(word: str, shape: str) -> None:
    assert is_secret_file_name(shape.format(w=word, W=word.upper()))


@pytest.mark.parametrize(
    "name",
    ["private_key", "api_key", "pass_word.txt", "pass-words.md", "pass_wd.txt", "pass word.txt", "PASS_WORD.TXT", "db.pass_word.conf"],
)  # fmt: skip
def test_a_split_or_joined_compound_still_marks_a_file(name: str) -> None:
    assert is_secret_file_name(name)


@pytest.mark.parametrize("name", ["pass_through.py", "seed_data.sql", "salt_states.sls", "cert_manager.md"])
def test_an_ambiguous_noun_alone_does_not_mark_a_file(name: str) -> None:
    assert not is_secret_file_name(name)


@pytest.mark.parametrize(
    "name", ["prod.env.json", "staging.env.yaml", "app.env.txt", "key.conf", "key.cfg", "keys.cfg"]
)
def test_an_env_file_with_a_data_suffix_and_a_bare_key_config_are_secret(name: str) -> None:
    """``*.env.*`` and the config suffixes the default ingest set now reaches (#19339 review)."""
    assert is_secret_file_name(name)


@pytest.mark.parametrize("name", ["environment.md", "envelope.json", "keyboard.conf", "monkey.cfg"])
def test_names_that_only_contain_env_or_key_are_not(name: str) -> None:
    assert not is_secret_file_name(name)
