"""Encryption tests using temporary files and mocked CLI actions."""

import configparser
from contextlib import contextmanager
import ntpath
import runpy
import threading
from types import SimpleNamespace
from typing import Callable, get_type_hints
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, rsa

from modules import encryption


PATH_OPTIONS = ("backup_dir", "private_key_path", "public_key_path")
WINDOWS_ROOT = r"C:\encryption-test\studio"


@pytest.fixture(autouse=True)
def mock_encryption_logger(monkeypatch):
    """Keep temporary filesystem paths out of application logs."""
    monkeypatch.setattr(encryption, "logger", Mock())


@pytest.fixture(scope="session")
def rsa_keys():
    """Use ephemeral 2048-bit keys to keep the unit tests fast."""
    return encryption.generate_rsa_keypair(key_size=2048)


@pytest.fixture(scope="session", params=["dsa", "ec"])
def non_rsa_key(request):
    """Provide real non-RSA keys to exercise PEM type validation."""
    if request.param == "dsa":
        return dsa.generate_private_key(key_size=2048)
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def key_files(tmp_path, rsa_keys):
    """Write keys only into the current test's temporary directory."""
    private_key, public_key = rsa_keys

    def write_keys(password=None):
        """Write temporary PEM files with optional private-key protection."""
        public_path = tmp_path / "public.pem"
        private_path = tmp_path / "private.pem"
        public_path.write_bytes(encryption.serialize_public_key(public_key))
        private_path.write_bytes(
            encryption.serialize_private_key(private_key, password)
        )
        return public_path, private_path

    return write_keys


@contextmanager
def _encryptor(public_path, private_path, folder, *, on_complete=None):
    """Always stop worker threads, including when an assertion fails."""
    instance = encryption.VideoEncryptor(
        public_path, private_path, folder, on_complete
    )
    try:
        yield instance
    finally:
        instance.stop()
        assert not instance._worker_thread.is_alive()


def _public_pem(private_key):
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _private_pem(private_key):
    return private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.mark.parametrize("size", [0, 1, 65536, 131089])
@pytest.mark.parametrize(
    "password", [None, b"test-only-passphrase"], ids=["plain-key", "protected"]
)
def test_file_round_trip(tmp_path, key_files, size, password):
    """Round-trip empty, small, and chunked payloads with either key format."""
    public_path, private_path = key_files(password)
    original = tmp_path / "input.bin"
    encoded = tmp_path / "input.bin.enc"
    restored = tmp_path / "restored.bin"
    payload = (bytes(range(256)) * ((size + 255) // 256))[:size]
    original.write_bytes(payload)

    with (
        _encryptor(public_path, private_path, tmp_path) as writer,
        _encryptor(public_path, private_path, tmp_path) as reader,
    ):
        writer.encrypt_file(public_path, original, encoded)
        assert not original.exists()
        reader.decrypt_file(private_path, encoded, restored, password=password)

    assert restored.read_bytes() == payload


@pytest.mark.parametrize("offset", [-1, -17], ids=["tag", "ciphertext"])
def test_tampering_removes_partial_output(tmp_path, key_files, offset):
    """Authentication failures must not leave unauthenticated plaintext."""
    public_path, private_path = key_files()
    original = tmp_path / "input.bin"
    encoded = tmp_path / "input.bin.enc"
    restored = tmp_path / "restored.bin"
    original.write_bytes(b"test-only-payload" * 100)

    with (
        _encryptor(public_path, private_path, tmp_path) as writer,
        _encryptor(public_path, private_path, tmp_path) as reader,
    ):
        writer.encrypt_file(public_path, original, encoded)
        content = bytearray(encoded.read_bytes())
        content[offset] ^= 1
        encoded.write_bytes(content)
        with pytest.raises(ValueError, match="authentication or integrity"):
            reader.decrypt_file(private_path, encoded, restored)

    assert not restored.exists()


@pytest.mark.parametrize("is_public", [True, False])
def test_key_loaders_reject_non_rsa_keys(non_rsa_key, is_public):
    """Valid PEM containing the wrong algorithm must be rejected."""
    if is_public:
        loader, pem = encryption.load_public_key, _public_pem(non_rsa_key)
    else:
        loader, pem = encryption.load_private_key, _private_pem(non_rsa_key)
    with pytest.raises(TypeError, match="Expected an RSA"):
        loader(pem)


@pytest.mark.parametrize(
    "loader", [encryption.load_public_key, encryption.load_private_key]
)
def test_key_loaders_reject_malformed_pem(loader):
    """Malformed input retains the PEM loader's ValueError behavior."""
    with pytest.raises(ValueError):
        loader(b"not a PEM key")


@pytest.mark.parametrize("password", [None, b"incorrect-passphrase"])
def test_private_key_rejects_missing_or_wrong_password(rsa_keys, password):
    """An encrypted private key requires its matching passphrase."""
    private_key, _ = rsa_keys
    pem = encryption.serialize_private_key(
        private_key, b"test-only-passphrase"
    )
    with pytest.raises((TypeError, ValueError)):
        encryption.load_private_key(pem, password)


def test_decryption_rejects_wrong_rsa_key(tmp_path, key_files):
    """An unrelated RSA key must not produce an output file."""
    public_path, private_path = key_files()
    original = tmp_path / "input.bin"
    encoded = tmp_path / "input.bin.enc"
    restored = tmp_path / "restored.bin"
    original.write_bytes(b"test-only-payload")
    wrong_private, _ = encryption.generate_rsa_keypair(key_size=2048)

    with _encryptor(public_path, private_path, tmp_path) as encryptor:
        encryptor.encrypt_file(public_path, original, encoded)
        private_path.write_bytes(_private_pem(wrong_private))
        with pytest.raises(ValueError):
            encryptor.decrypt_file(private_path, encoded, restored)

    assert not restored.exists()


@pytest.mark.parametrize("encrypting", [True, False])
def test_file_operations_wrap_non_rsa_key_errors(
    tmp_path, key_files, non_rsa_key, encrypting
):
    """Both file operations consistently wrap key-type errors as ValueError."""
    public_path, private_path = key_files()
    original = tmp_path / "input.bin"
    encoded = tmp_path / "input.bin.enc"
    restored = tmp_path / "restored.bin"
    original.write_bytes(b"test-only-payload")

    with _encryptor(public_path, private_path, tmp_path) as encryptor:
        if encrypting:
            public_path.write_bytes(_public_pem(non_rsa_key))
            with pytest.raises(ValueError) as caught:
                encryptor.encrypt_file(public_path, original, encoded)
            assert original.exists()
            assert not encoded.exists()
        else:
            encryptor.encrypt_file(public_path, original, encoded)
            private_path.write_bytes(_private_pem(non_rsa_key))
            with pytest.raises(ValueError) as caught:
                encryptor.decrypt_file(private_path, encoded, restored)
            assert not restored.exists()

    assert isinstance(caught.value.__cause__, TypeError)


def test_queue_encrypts_plain_files_and_skips_existing_outputs(
    tmp_path, key_files
):
    """Queue callbacks succeed without replacing already encrypted files."""
    public_path, private_path = key_files()
    backup = tmp_path / "backup"
    backup.mkdir()
    for index in range(3):
        (backup / f"{index}.bin").write_bytes(bytes([index]) * 100)
    (backup / "skip.bin").write_bytes(b"original")
    (backup / "skip.bin.enc").write_bytes(b"previous-output")
    completed = []
    finished = threading.Event()

    def on_complete(infile, success, remaining, error):
        """Signal completion after all three queued jobs report back."""
        completed.append((success, error))
        if len(completed) == 3:
            finished.set()

    with _encryptor(
        public_path, private_path, backup, on_complete=on_complete
    ) as encryptor:
        assert encryptor.encrypt_all_files() == 3
        assert finished.wait(10), "Encryption queue did not finish."
        assert completed == [(True, None)] * 3

    assert (backup / "skip.bin").read_bytes() == b"original"
    assert (backup / "skip.bin.enc").read_bytes() == b"previous-output"
    for index in range(3):
        assert not (backup / f"{index}.bin").exists()
        assert (backup / f"{index}.bin.enc").is_file()


def test_callback_and_rsa_return_annotations():
    """The callback allows None, and key loaders expose RSA return types."""
    hints = get_type_hints(encryption.VideoEncryptor.__init__)
    expected = Callable[[str, bool, int, str | None], None] | None
    assert hints["on_complete"] == expected
    assert (
        get_type_hints(encryption.load_public_key)["return"]
        is rsa.RSAPublicKey
    )
    assert (
        get_type_hints(encryption.load_private_key)["return"]
        is rsa.RSAPrivateKey
    )


@pytest.fixture
def cli_mocks(monkeypatch):
    """Prevent CLI menu choices from starting real operations or logging."""
    mocks = SimpleNamespace(
        input=Mock(side_effect=["1", "2", "3", "4"]),
        generate=Mock(),
        decrypt=Mock(),
        encrypt=Mock(),
    )
    monkeypatch.setattr("builtins.input", mocks.input)
    monkeypatch.setattr(encryption.logging, "basicConfig", Mock())
    monkeypatch.setattr(encryption, "cli_generate_keypair", mocks.generate)
    monkeypatch.setattr(encryption, "cli_decrypt_file", mocks.decrypt)
    monkeypatch.setattr(encryption, "cli_encrypt_file", mocks.encrypt)
    return mocks


@pytest.mark.parametrize("launch_dir", [".", "modules", "elsewhere"])
@pytest.mark.parametrize("absolute", [False, True])
def test_cli_finds_config_and_resolves_paths(
    tmp_path, monkeypatch, cli_mocks, launch_dir, absolute
):
    """Find config and resolve paths independently of the launch folder."""
    for name in ("config", "modules", "elsewhere"):
        (tmp_path / name).mkdir()
    expected = {
        "backup_dir": tmp_path / "backups",
        "private_key_path": tmp_path / "keys" / "private.pem",
        "public_key_path": tmp_path / "keys" / "public.pem",
    }
    config = configparser.ConfigParser()
    config["paths"] = {
        option: str(path) if absolute else str(path.relative_to(tmp_path))
        for option, path in expected.items()
    }
    with (tmp_path / "config" / "config.cfg").open("w") as config_file:
        config.write(config_file)
    monkeypatch.setattr(
        encryption, "__file__", str(tmp_path / "modules" / "encryption.py")
    )
    monkeypatch.chdir(tmp_path / launch_dir)

    encryption.main()

    cli_mocks.generate.assert_called_once_with(
        private_key_path=str(expected["private_key_path"]),
        public_key_path=str(expected["public_key_path"]),
    )
    for action in (cli_mocks.decrypt, cli_mocks.encrypt):
        action.assert_called_once_with(
            to_decrypt_folder=str(expected["backup_dir"]),
            to_encrypt_folder=str(expected["backup_dir"]),
            private_key_path=str(expected["private_key_path"]),
            public_key_path=str(expected["public_key_path"]),
        )


@pytest.fixture
def windows_cli(monkeypatch, cli_mocks):
    """Simulate Windows paths without changing the host OS path module."""
    values = {
        "backup_dir": "backups",
        "private_key_path": r"keys\private.pem",
        "public_key_path": r"keys\public.pem",
    }
    config = Mock()
    config.read.return_value = ["synthetic.cfg"]
    config.get.side_effect = lambda section, option: values[option]
    monkeypatch.setattr(encryption, "os", SimpleNamespace(path=ntpath))
    monkeypatch.setattr(
        encryption,
        "__file__",
        ntpath.join(WINDOWS_ROOT, "modules", "encryption.py"),
    )
    monkeypatch.setattr(
        encryption,
        "configparser",
        SimpleNamespace(ConfigParser=lambda: config),
    )
    return config, values


@pytest.mark.parametrize("option", PATH_OPTIONS)
@pytest.mark.parametrize("value", ["", "   "])
def test_cli_rejects_empty_paths(windows_cli, cli_mocks, option, value):
    """Blank config values must fail before any menu action is offered."""
    _, values = windows_cli
    values[option] = value
    with pytest.raises(ValueError, match="must not be empty"):
        encryption.main()
    cli_mocks.input.assert_not_called()
    cli_mocks.encrypt.assert_not_called()


@pytest.mark.parametrize("option", PATH_OPTIONS)
@pytest.mark.parametrize("value", [r"D:backups", r"C:backups", "D:", "C:"])
def test_cli_rejects_drive_relative_paths(
    windows_cli, cli_mocks, option, value
):
    """Reject drive-relative paths on both the project and another drive."""
    _, values = windows_cli
    values[option] = value
    with pytest.raises(ValueError, match="Drive-relative paths"):
        encryption.main()
    cli_mocks.input.assert_not_called()
    cli_mocks.encrypt.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("backups", ntpath.join(WINDOWS_ROOT, "backups")),
        (r".\backups", ntpath.join(WINDOWS_ROOT, r".\backups")),
        (r"..\backups", ntpath.join(WINDOWS_ROOT, r"..\backups")),
        (r"D:\backups", r"D:\backups"),
        (r"\\server\share\backups", r"\\server\share\backups"),
        (r"\backups", r"C:\backups"),
    ],
    ids=["relative", "dot", "parent", "absolute", "unc", "root-relative"],
)
def test_cli_resolves_windows_paths(windows_cli, cli_mocks, value, expected):
    """Support ordinary relative and fully qualified Windows paths."""
    config, values = windows_cli
    values.update(dict.fromkeys(PATH_OPTIONS, value))

    encryption.main()

    config.read.assert_called_once_with(
        ntpath.join(WINDOWS_ROOT, "config", "config.cfg")
    )
    cli_mocks.encrypt.assert_called_once_with(
        to_decrypt_folder=expected,
        to_encrypt_folder=expected,
        private_key_path=expected,
        public_key_path=expected,
    )
    assert ntpath.isabs(expected)


def test_cli_rejects_missing_config(windows_cli, cli_mocks):
    """An unreadable configuration must fail before entering the menu."""
    config, _ = windows_cli
    config.read.return_value = []
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        encryption.main()
    cli_mocks.input.assert_not_called()


def test_disabled_encryption_menu_can_quit(
    monkeypatch, windows_cli, cli_mocks
):
    """Option three remains Quit when the encryption menu item is disabled."""
    monkeypatch.setattr(encryption, "ENABLE_ENCRYPT_CLI", False)
    cli_mocks.input.side_effect = ["3"]

    encryption.main()

    cli_mocks.generate.assert_not_called()
    cli_mocks.decrypt.assert_not_called()
    cli_mocks.encrypt.assert_not_called()


def test_import_does_not_require_configuration(monkeypatch, tmp_path):
    """Application imports must not read configuration or create files."""
    config_factory = Mock(side_effect=AssertionError("Unexpected config read"))
    monkeypatch.setattr(configparser, "ConfigParser", config_factory)
    monkeypatch.chdir(tmp_path)

    namespace = runpy.run_path(
        encryption.__file__, run_name="encryption_import"
    )

    assert "VideoEncryptor" in namespace
    config_factory.assert_not_called()
    assert not list(tmp_path.iterdir())
