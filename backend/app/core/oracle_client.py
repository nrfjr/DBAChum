import logging
from pathlib import Path
from threading import Lock

import oracledb

from app.core.config import settings

logger = logging.getLogger(__name__)

_initialize_lock = Lock()
_initialized = False
_runtime_info: dict | None = None


def initialize_oracle_client() -> dict:
    """Initialize python-oracledb once and return runtime information."""
    global _initialized, _runtime_info

    if _initialized and _runtime_info is not None:
        return _runtime_info

    with _initialize_lock:
        if _initialized and _runtime_info is not None:
            return _runtime_info

        mode = settings.oracle_driver_mode

        if mode == "thin":
            _runtime_info = {
                "mode": "thin",
                "driver_version": oracledb.__version__,
                "client_version": None,
                "client_lib_dir": None,
            }
            _initialized = True
            logger.info(
                "Oracle driver initialized mode=thin driver=%s; "
                "Oracle 10g connectivity is unavailable in Thin mode",
                oracledb.__version__,
            )
            return _runtime_info

        lib_dir = settings.oracle_client_lib_dir
        if not lib_dir:
            raise RuntimeError(
                "ORACLE_CLIENT_LIB_DIR is required when "
                "ORACLE_DRIVER_MODE=thick."
            )

        client_dir = Path(lib_dir).expanduser()
        oci_dll = client_dir / "oci.dll"

        if not client_dir.is_dir() or not oci_dll.is_file():
            raise RuntimeError(
                "Oracle Thick mode is configured but oci.dll was not "
                f"found at {oci_dll}."
            )

        try:
            oracledb.init_oracle_client(
                lib_dir=str(client_dir)
            )
            client_version = oracledb.clientversion()
        except oracledb.Error as exc:
            raise RuntimeError(
                "Oracle Thick mode initialization failed for "
                f"{client_dir}: {exc}"
            ) from exc

        _runtime_info = {
            "mode": "thick",
            "driver_version": oracledb.__version__,
            "client_version": client_version,
            "client_lib_dir": str(client_dir),
        }
        _initialized = True

        logger.info(
            "Oracle driver initialized mode=thick driver=%s client=%s lib_dir=%s",
            oracledb.__version__,
            ".".join(str(part) for part in client_version),
            client_dir,
        )
        return _runtime_info
