"""
Unit and regression tests for scripts/setup_models.py.
Verifies cryptographic validation, atomic writes, idempotency, local file imports,
and corrupt download rejection using mocks without external network calls.
"""

import hashlib
import io
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.setup_models import (
    compute_sha256,
    verify_file_hash,
    download_model,
    import_local_model,
    main,
    PINNED_SHA256,
)


@pytest.fixture
def dummy_model(tmp_path):
    """Creates a temporary valid dummy file and returns (path, hash, content)."""
    content = b"DUMMY_YOLOX_NANO_MODEL_WEIGHTS_FOR_TESTING_12345"
    digest = hashlib.sha256(content).hexdigest().lower()
    file_path = tmp_path / "valid_model.onnx"
    file_path.write_bytes(content)
    return file_path, digest, content


def test_compute_sha256_and_verify_file_hash(dummy_model, tmp_path):
    file_path, digest, _ = dummy_model
    assert compute_sha256(file_path) == digest
    assert verify_file_hash(file_path, digest) is True
    assert verify_file_hash(file_path, "0" * 64) is False
    assert verify_file_hash(tmp_path / "non_existent.onnx", digest) is False


def test_download_model_idempotent_when_valid_exists(dummy_model):
    """When valid file already exists, download_model does not hit network."""
    file_path, digest, _ = dummy_model

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = download_model(
            url="http://mock.test/model.onnx",
            dest_path=file_path,
            expected_sha=digest,
            force=False
        )
        assert result is True
        mock_urlopen.assert_not_called()


def test_download_model_success_with_atomic_replacement(tmp_path):
    """Verifies that downloaded stream is verified and atomically installed."""
    content = b"STREAMED_ONNX_BYTES_VALID_HASH"
    digest = hashlib.sha256(content).hexdigest().lower()
    dest = tmp_path / "dest" / "yolox_nano.onnx"

    mock_resp = MagicMock()
    mock_resp.read.side_effect = [content, b""]
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = download_model(
            url="http://mock.test/model.onnx",
            dest_path=dest,
            expected_sha=digest,
            force=True
        )
        assert result is True
        mock_urlopen.assert_called_once()
        assert dest.is_file()
        assert dest.read_bytes() == content

        # Verify no orphaned .tmp files left
        tmp_files = list(dest.parent.glob("*.tmp*"))
        assert len(tmp_files) == 0


def test_download_model_hash_mismatch_cleans_up_and_fails(tmp_path):
    """Verifies that hash mismatch rejects the download and purges .tmp file."""
    content = b"TAMPERED_OR_CORRUPT_BYTES"
    dest = tmp_path / "dest" / "yolox_nano.onnx"
    expected_digest = "a" * 64

    mock_resp = MagicMock()
    mock_resp.read.side_effect = [content, b""]
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = download_model(
            url="http://mock.test/model.onnx",
            dest_path=dest,
            expected_sha=expected_digest,
            force=True
        )
        assert result is False
        assert not dest.exists(), "Target file must not be created on hash failure"
        tmp_files = list(dest.parent.glob("*.tmp*"))
        assert len(tmp_files) == 0, "Temporary files must be cleaned up on failure"


def test_download_model_network_exception_cleanup(tmp_path):
    """Verifies that an urllib exception during download cleans up temporary files."""
    dest = tmp_path / "dest" / "yolox_nano.onnx"

    with patch("urllib.request.urlopen", side_effect=OSError("Connection reset")):
        result = download_model(
            url="http://mock.test/model.onnx",
            dest_path=dest,
            expected_sha="b" * 64
        )
        assert result is False
        assert not dest.exists()
        tmp_files = list(dest.parent.glob("*.tmp*"))
        assert len(tmp_files) == 0


def test_import_local_model_success_and_validation(dummy_model, tmp_path):
    """Verifies local import with cryptographic verification and atomic placement."""
    src_file, digest, content = dummy_model
    dest_file = tmp_path / "imported" / "model.onnx"

    # Successful import
    res = import_local_model(
        src_path=src_file,
        dest_path=dest_file,
        expected_sha=digest
    )
    assert res is True
    assert dest_file.is_file()
    assert dest_file.read_bytes() == content

    # Tampered file import rejected
    bad_file = tmp_path / "bad.onnx"
    bad_file.write_bytes(b"BAD_DATA")
    res_bad = import_local_model(
        src_path=bad_file,
        dest_path=tmp_path / "imported_bad.onnx",
        expected_sha=digest
    )
    assert res_bad is False


def test_main_cli_check_only(dummy_model, tmp_path):
    """Verifies CLI behavior with --check-only flag."""
    src_file, digest, _ = dummy_model

    # Valid file check -> exit 0
    with patch("sys.argv", ["setup_models.py", "--dest", str(src_file), "--expected-sha", digest, "--check-only"]):
        exit_code = main()
        assert exit_code == 0

    # Non-existent file check -> exit 1
    with patch("sys.argv", ["setup_models.py", "--dest", str(tmp_path / "none.onnx"), "--check-only"]):
        exit_code = main()
        assert exit_code == 1

    # Mismatched hash check -> exit 1
    with patch("sys.argv", ["setup_models.py", "--dest", str(src_file), "--expected-sha", "0" * 64, "--check-only"]):
        exit_code = main()
        assert exit_code == 1
