"""Reading .env. The file is hand-edited and also sourced by the launchd wrapper,
so the two readers must agree on what it says."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.briefs.envfile import environment, read_env_file


def _read(body):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    with open(path, "w") as fh:
        fh.write(body)
    try:
        return read_env_file(path)
    finally:
        os.unlink(path)


@pytest.mark.parametrize("body,expected", [
    ("export SMTP_USER=a@b.test\n", {"SMTP_USER": "a@b.test"}),
    ("export\tSMTP_USER=a@b.test\n", {"SMTP_USER": "a@b.test"}),
    ("  export SMTP_USER=a@b.test\n", {"SMTP_USER": "a@b.test"}),
])
def test_an_export_prefix_is_not_part_of_the_name(body, expected):
    """`export VAR=value` is valid in a file meant to be sourced, and the launchd
    wrapper does source it with `set -a`. Reading the key as "export VAR" makes the
    same file work under the scheduler and fail for every script that reads it."""
    assert _read(body) == expected


def test_a_value_may_contain_equals_signs():
    assert _read("TOKEN=abc=def==\n") == {"TOKEN": "abc=def=="}


def test_quotes_are_stripped_because_sourcing_strips_them():
    assert _read('NOTE="a b c"\n') == {"NOTE": "a b c"}
    assert _read("NOTE='a b'\n") == {"NOTE": "a b"}


def test_comments_and_blank_lines_are_ignored():
    assert _read("\n# a comment\n\nSMTP_PORT=587\n") == {"SMTP_PORT": "587"}


def test_a_windows_line_ending_does_not_end_up_in_the_value():
    """A 16-character app password with \\r appended fails at the server with no
    explanation."""
    assert _read("SMTP_USER=a@b.test\r\nSMTP_PORT=587\r\n")["SMTP_PORT"] == "587"


def test_a_file_without_a_trailing_newline_is_read():
    assert _read("SMTP_PORT=587") == {"SMTP_PORT": "587"}


def test_a_missing_file_is_empty_not_an_error():
    assert read_env_file("/no/such/.env") == {}


def test_the_real_environment_wins_over_the_file(monkeypatch):
    """An explicit `export` on the command line must override the file."""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    with open(path, "w") as fh:
        fh.write("SMTP_PORT=587\n")
    monkeypatch.setenv("SMTP_PORT", "2525")
    try:
        assert environment(path)["SMTP_PORT"] == "2525"
    finally:
        os.unlink(path)
