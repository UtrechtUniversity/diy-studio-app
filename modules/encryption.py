import configparser
import json
import logging
import os
import queue
import struct
import sys
import threading
from getpass import getpass
from typing import Callable, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# =========================
# CONFIG CONSTANTS
# =========================
config = configparser.ConfigParser()
config.read(os.path.join("config", "config.cfg"))

logger = logging.getLogger(__name__)

BASE_FOLDER = os.path.join(config.get("paths", "backup_dir"))
# Folder that contains encrypted files used by the CLI
TO_ENCRYPT_FOLDER = os.path.join(BASE_FOLDER, "")
TO_DECRYPT_FOLDER = os.path.join(BASE_FOLDER, "")

# Paths where the RSA keys are stored
PRIVATE_KEY_PATH = os.path.join(config.get("paths", "private_key_path"))
PUBLIC_KEY_PATH = os.path.join(config.get("paths", "public_key_path"))

# Enable or disable the "encrypt file" menu option
ENABLE_ENCRYPT_CLI = True

# =========================
# FILE FORMAT CONSTANTS
# =========================

MAGIC = b"HYBRID1"        # magic string to identify file type
HEADER_LEN_SIZE = 8       # 8-byte big-endian header length
GCM_TAG_LEN = 16          # bytes
AES_KEY_SIZE = 32         # 256-bit AES key
GCM_IV_SIZE = 12          # 96-bit nonce
CHUNK_SIZE = 64 * 1024    # 64KB chunk size

# =========================
# KEY UTILITIES
# =========================

def generate_rsa_keypair(key_size: int = 4096):
    """
    Generate a new RSA keypair in memory.

    Returns (private_key, public_key) as cryptography key objects.
    """
    private = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend(),
    )
    public = private.public_key()
    return private, public

def serialize_public_key(pubkey) -> bytes:
    """
    Serialize a public key object to PEM bytes.
    """
    return pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

def serialize_private_key(
    privkey,
    password: Optional[bytes] = None,
) -> bytes:
    """
    Serialize a private key object to PEM bytes.

    If password is provided, encrypt the PEM with that password.
    """
    enc = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return privkey.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=enc,
    )

def load_public_key(pem_bytes: bytes):
    """
    Load a public key from PEM bytes.
    """
    return serialization.load_pem_public_key(
        pem_bytes,
        backend=default_backend(),
    )

def load_private_key(
    pem_bytes: bytes,
    password: Optional[bytes] = None,
):
    """
    Load a private key from PEM bytes.
    """
    return serialization.load_pem_private_key(
        pem_bytes,
        password=password,
        backend=default_backend(),
    )

# =========================
# VIDEO ENCRYPTOR CLASS
# =========================

class VideoEncryptor:
    """
    Queued encryptor that uses a hybrid RSA + AES-GCM scheme.

    File format:
      [8-byte header_len][header JSON][encrypted key][ciphertext...][tag]
    """

    def __init__(
        self,
        public_key_path,
        private_key_path,
        encrypt_folder,
        on_complete: Optional[
            Callable[[str, bool, int, Optional[str]], None]
        ] = None,
    ):
        """
        :param on_complete:
            callback called when a file finishes encrypting:
            on_complete(input, success, num_remaining, error_message)
        """
        self.PUBLIC_KEY_PATH = public_key_path
        self.PRIVATE_KEY_PATH = private_key_path
        self.TO_ENCRYPT_FOLDER = encrypt_folder
        self.on_complete = on_complete
        self._queue: queue.Queue = queue.Queue()
        self._stop_flag = threading.Event()
        self._worker_thread = threading.Thread(
            name="VideoEncryptor",
            target=self._process_queue,
            daemon=True,
        )

    # -----------------------------
    # Public methods
    # -----------------------------

    def encrypt_all_files(self):
        """
        Enqueue encryption jobs for all files in TO_ENCRYPT_FOLDER.

        Uses PUBLIC_KEY_PATH and writes .enc files to TO_DECRYPT_FOLDER.
        For each completed file, the on_complete callback is fired.
        """
        logger.info("Encryptor : starting encryption of all files.")
        i = 0

        self._worker_thread.start()

        if not os.path.isfile(self.PUBLIC_KEY_PATH):
            raise FileNotFoundError(
                f"Encryptor : Public key file not found: {self.PUBLIC_KEY_PATH}"
            )

        ensure_folder(self.TO_ENCRYPT_FOLDER)

        files = [
            name
            for name in os.listdir(self.TO_ENCRYPT_FOLDER)
            if os.path.isfile(os.path.join(self.TO_ENCRYPT_FOLDER, name))
        ]

        if not files:
            logger.info(f"Encryptor : No files found in: {self.TO_ENCRYPT_FOLDER}")
            return i

        for filename in files:
            if filename.lower().endswith(".enc"):
                # File is encoded already, skip
                continue

            input_path = os.path.join(self.TO_ENCRYPT_FOLDER, filename)
            out_name = filename + ".enc"
            output_path = os.path.join(self.TO_ENCRYPT_FOLDER, out_name)

            if os.path.exists(output_path):
                logger.info(
                    f"Encryptor : Skipping {filename}: encrypted file already "
                    f"exists at {output_path}"
                )
                continue

            self.enqueue_encryption(
                self.PUBLIC_KEY_PATH,
                input_path,
                output_path,
            )

            i += 1

        return i

    def enqueue_encryption(
        self,
        public_key_pem_path: str,
        input_path: str,
        output_path: str,
    ) -> None:
        """
        Add a file to the encryption queue.

        public_key_pem_path is a filesystem path to a PEM public key.
        """
        self._queue.put((public_key_pem_path, input_path, output_path))

    def stop(self) -> None:
        """Stop the background thread after finishing current job."""
        self._stop_flag.set()
        self._queue.put(None)  # unblock queue

        if self._worker_thread is not None and self._worker_thread.is_alive():
            if threading.current_thread() is not self._worker_thread:
                self._worker_thread.join(timeout=2.0)

    # -----------------------------
    # Internal: queue processing
    # -----------------------------

    def _process_queue(self) -> None:
        while not self._stop_flag.is_set():
            job = self._queue.get()
            if job is None:
                break
            pubkey_path, infile, outfile = job
            try:
                self.encrypt_file(pubkey_path, infile, outfile)
                if self.on_complete:
                    self.on_complete(infile, True, self._queue.qsize(), None)
            except Exception as e:
                logger.error(f"Encryptor : error while encrypting file : {e}")
                if self.on_complete:
                    self.on_complete(infile, False, self._queue.qsize(), str(e))

    # -----------------------------
    # Encryption / decryption
    # -----------------------------

    def encrypt_file(
        self,
        public_key_pem_path: str,
        input_path: str,
        output_path: str,
    ) -> None:
        """
        Encrypt input_path to output_path.

        Uses:
          - random AES-256 key
          - AES-GCM for file contents
          - RSA-OAEP for the AES key
        """
        logger.info("Encryptor : starting file encryption.")

        if not os.path.isfile(input_path):
            msg = f"Input file not found: {input_path}"
            raise FileNotFoundError(msg)

        if not os.path.isfile(public_key_pem_path):
            msg = f"Public key file not found: {public_key_pem_path}"
            raise FileNotFoundError(msg)

        with open(public_key_pem_path, "rb") as pub_file:
            pub_pem = pub_file.read()

        try:
            public_key = load_public_key(pub_pem)
        except ValueError as exc:
            msg = "Could not load public key (corrupted key file?)."
            raise ValueError(msg) from exc

        aes_key = os.urandom(AES_KEY_SIZE)
        iv = os.urandom(GCM_IV_SIZE)

        enc_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        header = {
            "magic": MAGIC.decode("ascii"),
            "version": 1,
            "enc_key_len": len(enc_key),
            "enc_key_algo": "RSA-OAEP-SHA256",
            "cipher": "AES-GCM",
            "aes_key_len": AES_KEY_SIZE,
            "iv": iv.hex(),
        }
        header_bytes = json.dumps(header).encode("utf-8")

        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()

        with open(input_path, "rb") as fin, open(
            output_path,
            "wb",
        ) as fout:
            fout.write(struct.pack(">Q", len(header_bytes)))
            fout.write(header_bytes)
            fout.write(enc_key)

            while True:
                chunk = fin.read(CHUNK_SIZE)
                if not chunk:
                    break
                ct = encryptor.update(chunk)
                if ct:
                    fout.write(ct)

            final = encryptor.finalize()
            if final:
                fout.write(final)

            tag = encryptor.tag
            fout.write(tag)

        logger.info(f"Encryptor : [OK] Encrypted: {input_path} -> {output_path}")

        # Delete original file after successful encryption
        try:
            os.remove(input_path)
            logger.info(f"Encryptor : [OK] Deleted original file: {input_path}")
        except OSError as exc:
            logger.warning(
                f"Encryptor: : Could not delete original file {input_path}: {exc}"
            )

    def decrypt_file(
        self,
        private_key_pem_path: str,
        input_path: str,
        output_path: str,
        password: Optional[bytes] = None,
    ) -> None:
        """
        Decrypt a file created by encrypt_file.

        Removes partial output if authentication fails.
        """
        if not os.path.isfile(input_path):
            msg = f"Encrypted input file not found: {input_path}"
            raise FileNotFoundError(msg)

        if not os.path.isfile(private_key_pem_path):
            msg = f"Private key file not found: {private_key_pem_path}"
            raise FileNotFoundError(msg)

        with open(private_key_pem_path, "rb") as priv_file:
            priv_pem = priv_file.read()

        try:
            private_key = load_private_key(priv_pem, password=password)
        except (TypeError, ValueError) as exc:
            msg = (
                "Could not load private key. Wrong passphrase or "
                "corrupted key file."
            )
            raise ValueError(msg) from exc

        total_size = os.path.getsize(input_path)

        with open(input_path, "rb") as fin:
            header_len_packed = fin.read(HEADER_LEN_SIZE)
            if len(header_len_packed) != HEADER_LEN_SIZE:
                msg = "Invalid or corrupted file (missing header length)."
                raise ValueError(msg)

            header_len = struct.unpack(">Q", header_len_packed)[0]
            header_bytes = fin.read(header_len)
            if len(header_bytes) != header_len:
                msg = "Invalid or corrupted file (missing full header)."
                raise ValueError(msg)

            header = json.loads(header_bytes.decode("utf-8"))

            if header.get("magic") != MAGIC.decode("ascii"):
                msg = "Not a valid encrypted file (magic mismatch)."
                raise ValueError(msg)

            enc_key_len = header["enc_key_len"]
            iv = bytes.fromhex(header["iv"])

            enc_key = fin.read(enc_key_len)
            if len(enc_key) != enc_key_len:
                msg = "Invalid or corrupted file (missing encrypted key)."
                raise ValueError(msg)

            header_total_size = HEADER_LEN_SIZE + header_len + enc_key_len

            if total_size < header_total_size + GCM_TAG_LEN:
                msg = "Invalid or corrupted file (no ciphertext/tag)."
                raise ValueError(msg)

            tag_offset = total_size - GCM_TAG_LEN
            fin.seek(tag_offset)
            tag = fin.read(GCM_TAG_LEN)
            if len(tag) != GCM_TAG_LEN:
                msg = "Invalid or corrupted file (tag truncated)."
                raise ValueError(msg)

            aes_key = private_key.decrypt(
                enc_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            cipher = Cipher(
                algorithms.AES(aes_key),
                modes.GCM(iv, tag),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()

            fin.seek(header_total_size)
            bytes_left = tag_offset - header_total_size

            with open(output_path, "wb") as fout:
                try:
                    while bytes_left > 0:
                        to_read = min(CHUNK_SIZE, bytes_left)
                        chunk = fin.read(to_read)
                        if not chunk:
                            break
                        pt = decryptor.update(chunk)
                        if pt:
                            fout.write(pt)
                        bytes_left -= len(chunk)

                    final = decryptor.finalize()
                    if final:
                        fout.write(final)
                except Exception as exc:  # noqa: BLE001
                    fout.close()
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                    msg = (
                        "Decryption failed "
                        "(authentication or integrity error)."
                    )
                    raise ValueError(msg) from exc

        logger.info(f"[OK] Decrypted: {input_path} -> {output_path}")

# =========================
# CLI HELPERS
# =========================


def ensure_folder(path: str) -> None:
    """Create folder if it does not exist."""
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def cli_generate_keypair() -> None:
    """
    CLI routine to generate an RSA keypair and save it.

    Asks for a passphrase and writes keys to PRIVATE_KEY_PATH and
    PUBLIC_KEY_PATH.
    """
    ensure_folder(os.path.dirname(PRIVATE_KEY_PATH))
    ensure_folder(os.path.dirname(PUBLIC_KEY_PATH))

    if os.path.exists(PRIVATE_KEY_PATH) or os.path.exists(PUBLIC_KEY_PATH):
        print("Warning: key files already exist.")
        answer = input("Overwrite existing keys? (y/N): ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted key generation.")
            return

    print("Generating RSA keypair (this may take a moment)...")
    private_key, public_key = generate_rsa_keypair()

    passphrase = getpass(
        "Enter passphrase to protect the private key "
        "(leave empty for none): "
    )
    if passphrase:
        password_bytes = passphrase.encode("utf-8")
    else:
        password_bytes = None

    priv_pem = serialize_private_key(private_key, password=password_bytes)
    pub_pem = serialize_public_key(public_key)

    with open(PRIVATE_KEY_PATH, "wb") as priv_file:
        priv_file.write(priv_pem)

    with open(PUBLIC_KEY_PATH, "wb") as pub_file:
        pub_file.write(pub_pem)

    print(f"Private key saved to: {PRIVATE_KEY_PATH}")
    print(f"Public key saved to:  {PUBLIC_KEY_PATH}")


def cli_decrypt_file() -> None:
    """
    CLI routine to list encrypted files and decrypt one.

    Uses PRIVATE_KEY_PATH and TO_DECRYPT_FOLDER.
    """
    ensure_folder(TO_DECRYPT_FOLDER)

    files = sorted(
        name
        for name in os.listdir(TO_DECRYPT_FOLDER)
        if os.path.isfile(os.path.join(TO_DECRYPT_FOLDER, name))
        and name.lower().endswith(".enc")
    )

    if not files:
        print(f"No .enc files found in {TO_DECRYPT_FOLDER}")
        return

    print("Encrypted files:")
    for index, name in enumerate(files, start=1):
        print(f"{index}. {name}")

    while True:
        choice = input(
            "Enter the number of the file to decrypt (or 'q' to quit): "
        ).strip()
        if choice.lower() in ("q", "quit", "exit"):
            return
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue

        number = int(choice)
        if 1 <= number <= len(files):
            chosen_file = files[number - 1]
            break
        print(f"Please enter a number between 1 and {len(files)}.")

    enc_path = os.path.join(TO_DECRYPT_FOLDER, chosen_file)

    if chosen_file.lower().endswith(".enc"):
        out_name = chosen_file[:-4]
    else:
        out_name = chosen_file + ".dec"

    out_path = os.path.join(TO_DECRYPT_FOLDER, out_name)

    if not os.path.isfile(PRIVATE_KEY_PATH):
        print(f"Private key file not found: {PRIVATE_KEY_PATH}")
        return

    passphrase = getpass(
        "Enter passphrase for private key "
        "(leave empty if none): "
    )
    if passphrase:
        password_bytes = passphrase.encode("utf-8")
    else:
        password_bytes = None

    if os.path.exists(out_path):
        answer = input(
            "Output file already exists. Overwrite? (y/N): "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted decryption.")
            return

    encryptor = VideoEncryptor(
        PUBLIC_KEY_PATH,
        PRIVATE_KEY_PATH,
        TO_ENCRYPT_FOLDER,
    )

    try:
        encryptor.decrypt_file(
            PRIVATE_KEY_PATH,
            enc_path,
            out_path,
            password=password_bytes,
        )
        print(f"Decrypted file written to: {out_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error during decryption: {exc}")
    finally:
        del encryptor


def cli_encrypt_file() -> None:
    """
    CLI routine to encrypt a single file.

    Lists files inside TO_ENCRYPT_FOLDER and lets the user choose one
    by number. Uses PUBLIC_KEY_PATH and writes the .enc file into
    TO_DECRYPT_FOLDER.
    """
    if not os.path.isfile(PUBLIC_KEY_PATH):
        print(f"Public key file not found: {PUBLIC_KEY_PATH}")
        print("Generate a keypair first.")
        return

    ensure_folder(TO_ENCRYPT_FOLDER)
    ensure_folder(TO_DECRYPT_FOLDER)

    # List available files to encrypt
    files = sorted(
        name
        for name in os.listdir(TO_ENCRYPT_FOLDER)
        if os.path.isfile(os.path.join(TO_ENCRYPT_FOLDER, name))
    )

    if not files:
        print(f"No files found in: {TO_ENCRYPT_FOLDER}")
        return

    print("Files available for encryption:")
    for index, name in enumerate(files, start=1):
        print(f"{index}. {name}")

    # Ask user to pick a file
    while True:
        choice = input(
            "Enter the number of the file to encrypt (or 'q' to quit): "
        ).strip()

        if choice.lower() in ("q", "quit", "exit"):
            return

        if not choice.isdigit():
            print("Please enter a valid number.")
            continue

        number = int(choice)
        if 1 <= number <= len(files):
            chosen_file = files[number - 1]
            break

        print(f"Please enter a number between 1 and {len(files)}.")

    input_path = os.path.join(TO_ENCRYPT_FOLDER, chosen_file)

    out_name = chosen_file + ".enc"
    out_path = os.path.join(TO_DECRYPT_FOLDER, out_name)

    if os.path.exists(out_path):
        answer = input(
            "Encrypted output already exists. Overwrite? (y/N): "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted encryption.")
            return

    encryptor = VideoEncryptor(
        PUBLIC_KEY_PATH,
        PRIVATE_KEY_PATH,
        TO_ENCRYPT_FOLDER,
    )

    try:
        encryptor.encrypt_file(PUBLIC_KEY_PATH, input_path, out_path)
        print(f"Encrypted file written to: {out_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error during encryption: {exc}")
    finally:
        encryptor.stop()


# =========================
# MAIN CLI ENTRY
# =========================

def main() -> None:
    """
    Simple text menu for key management, encryption and decryption.
    """

    log_filename = "log.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_filename, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

    while True:
        print()
        print("1. Generate RSA keypair")
        print("2. Decrypt an encrypted file")
        if ENABLE_ENCRYPT_CLI:
            print("3. Encrypt a file")
            print("4. Quit")
        else:
            print("3. Quit")

        choice = input("Select an option: ").strip()

        if choice == "1":
            cli_generate_keypair()
        elif choice == "2":
            cli_decrypt_file()
        elif ENABLE_ENCRYPT_CLI and choice == "3":
            cli_encrypt_file()
        elif (not ENABLE_ENCRYPT_CLI and choice == "3") or (
            ENABLE_ENCRYPT_CLI and choice == "4"
        ):
            print("Quitting.")
            break
        else:
            print("Invalid option. Please choose a valid menu number.")


if __name__ == "__main__":
    main()
