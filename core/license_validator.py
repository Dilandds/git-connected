"""
License and subscription validation module.

Supports monthly subscription activation and refresh across Windows and macOS.
Falls back to the legacy GitHub Gist key list when no API base URL is configured.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

LEGACY_GIST_URL = "https://gist.githubusercontent.com/Dilandds/bd5c8db0157c16dc2473a8d1fe368b44/raw/valid_licenses.json"

REQUEST_TIMEOUT = int(os.environ.get("ECTOFORM_LICENSE_TIMEOUT", "10"))
CACHE_EXPIRY_DAYS = int(os.environ.get("ECTOFORM_LICENSE_CACHE_DAYS", "7"))
OFFLINE_GRACE_DAYS = int(os.environ.get("ECTOFORM_LICENSE_OFFLINE_GRACE_DAYS", "7"))
LICENSE_API_BASE_URL = os.environ.get("ECTOFORM_LICENSE_API_URL", "").strip().rstrip("/")
BUY_URL = os.environ.get("ECTOFORM_BUY_URL", "").strip()
MANAGE_URL = os.environ.get("ECTOFORM_MANAGE_URL", "").strip()
SUPPORT_URL = os.environ.get("ECTOFORM_SUPPORT_URL", "").strip()
APP_VERSION = os.environ.get("ECTOFORM_APP_VERSION", "1.0.0")

_ALLOWED_ACTIVE_STATUSES = {"active", "trialing", "past_due", "offline_grace"}
_BLOCKED_STATUSES = {"canceled", "expired", "revoked", "seat_limit_reached"}


def get_config_directory() -> Path:
    """Get the configuration directory for storing license data."""
    if sys.platform == "darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "ECTOFORM"
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            config_dir = Path(local_app_data) / "ECTOFORM"
        else:
            config_dir = Path.home() / "AppData" / "Local" / "ECTOFORM"
    else:
        config_dir = Path.home() / ".config" / "ectoform"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_license_storage_path() -> Path:
    """Get the path to the license storage file."""
    return get_config_directory() / "license.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_status(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    return str(value).strip().lower()


def _normalize_license_key(license_key: str) -> str:
    return (license_key or "").strip().upper()


def _normalize_contact_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "@" in value and not value.startswith(("mailto:", "http://", "https://")):
        return f"mailto:{value}"
    return value


def get_buy_url() -> str:
    return BUY_URL


def get_manage_url() -> str:
    return MANAGE_URL


def get_support_url() -> str:
    return _normalize_contact_url(SUPPORT_URL)


def get_license_record() -> Dict[str, Any]:
    """Load the current license record from local storage."""
    storage_path = get_license_storage_path()
    if not storage_path.exists():
        return {}

    try:
        with open(storage_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, IOError, OSError):
        pass

    return {}


def save_license_record(record: Dict[str, Any]) -> None:
    """Persist the license record to local storage."""
    storage_path = get_license_storage_path()
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(storage_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
    except IOError:
        pass


def _merge_subscription_state(record: Dict[str, Any], subscription_payload: Dict[str, Any]) -> Dict[str, Any]:
    subscription = dict(record.get("subscription") or {})
    subscription.update(subscription_payload)
    record["subscription"] = subscription
    return record


def _build_subscription_state(
    license_key: str,
    user_identifier: Optional[str],
    machine_fingerprint: Optional[str],
    response: Dict[str, Any],
    existing_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = response.get("subscription") if isinstance(response.get("subscription"), dict) else {}
    existing_subscription = {}
    if isinstance(existing_record, dict) and isinstance(existing_record.get("subscription"), dict):
        existing_subscription = existing_record.get("subscription", {})

    status = _normalize_status(response.get("status") or payload.get("status") or existing_subscription.get("status") or "active")
    activation_token = response.get("activation_token") or payload.get("activation_token") or (existing_record or {}).get("activation_token")
    expiry_value = response.get("expires_at") or payload.get("expires_at") or existing_subscription.get("expires_at")
    management_url = response.get("management_url") or payload.get("management_url") or existing_subscription.get("management_url") or get_manage_url()
    renewal_url = response.get("renewal_url") or payload.get("renewal_url") or existing_subscription.get("renewal_url") or get_buy_url()

    subscription_state: Dict[str, Any] = {
        "status": status,
        "expires_at": expiry_value,
        "seat_limit": response.get("seat_limit") or payload.get("seat_limit") or existing_subscription.get("seat_limit"),
        "seats_used": response.get("seats_used") or payload.get("seats_used") or existing_subscription.get("seats_used"),
        "company_id": response.get("company_id") or payload.get("company_id") or existing_subscription.get("company_id"),
        "user_id": response.get("user_id") or payload.get("user_id") or existing_subscription.get("user_id"),
        "management_url": management_url,
        "renewal_url": renewal_url,
        "last_synced_at": _iso_now(),
        "offline_grace_expires_at": (_utcnow() + timedelta(days=OFFLINE_GRACE_DAYS)).isoformat(),
    }

    record: Dict[str, Any] = {
        "license_key": _normalize_license_key(license_key),
        "validated_at": _iso_now(),
        "activation_token": activation_token,
        "user_identifier": (user_identifier or "").strip(),
        "machine_fingerprint": (machine_fingerprint or "").strip(),
        "source": "subscription",
    }

    if activation_token:
        record["activation_token"] = activation_token

    record = _merge_subscription_state(record, subscription_state)

    if response.get("cached_valid_keys") and isinstance(response.get("cached_valid_keys"), list):
        record["cached_valid_keys"] = response["cached_valid_keys"]
        record["cached_at"] = _iso_now()

    return record


def store_license_key(license_key: str, valid_keys: Optional[List[str]] = None) -> None:
    """Store the license key and optionally cache valid keys.

    This preserves the older file structure for legacy validation paths.
    """
    record = get_license_record()
    record["license_key"] = _normalize_license_key(license_key)
    record["validated_at"] = _iso_now()

    if valid_keys:
        record["cached_valid_keys"] = valid_keys
        record["cached_at"] = _iso_now()

    save_license_record(record)


def get_stored_license_key() -> Optional[str]:
    """Get the stored license key from local storage."""
    record = get_license_record()
    license_key = record.get("license_key")
    if isinstance(license_key, str) and license_key.strip():
        return license_key.strip()
    return None


def get_cached_valid_keys() -> Optional[List[str]]:
    """Get cached valid keys from local storage."""
    record = get_license_record()
    cached_keys = record.get("cached_valid_keys")
    if not isinstance(cached_keys, list):
        return None

    cached_at = _parse_datetime(record.get("cached_at"))
    if cached_at and (_utcnow() - cached_at).days > CACHE_EXPIRY_DAYS:
        return None

    return cached_keys


def fetch_valid_keys_from_gist(gist_url: str = LEGACY_GIST_URL) -> Tuple[Optional[List[str]], Optional[str]]:
    """Fetch valid license keys from GitHub Gist for legacy compatibility."""
    try:
        response = requests.get(gist_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()
        valid_keys = data.get("valid_keys", [])

        if not isinstance(valid_keys, list):
            return None, "Invalid Gist format: 'valid_keys' must be a list"

        return valid_keys, None

    except requests.exceptions.Timeout:
        return None, "Request timed out. Please check your internet connection."
    except requests.exceptions.ConnectionError:
        return None, "Connection error. Please check your internet connection."
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error: {e.response.status_code}"
    except json.JSONDecodeError:
        return None, "Invalid JSON response from Gist"
    except KeyError:
        return None, "Invalid Gist format: 'valid_keys' key not found"
    except Exception as e:
        return None, f"Error fetching keys: {str(e)}"


def validate_license_key(license_key: str, valid_keys: List[str]) -> bool:
    """Validate a license key against a list of valid keys."""
    if not license_key or not valid_keys:
        return False

    normalized_license_key = _normalize_license_key(license_key)
    normalized_valid_keys = [_normalize_license_key(key) for key in valid_keys]
    return normalized_license_key in normalized_valid_keys


def _api_url(path: str) -> str:
    return f"{LICENSE_API_BASE_URL}/{path.lstrip('/')}"


def _request_json(method: str, path: str, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not LICENSE_API_BASE_URL:
        return None, "License API URL is not configured"

    try:
        response = requests.request(
            method=method,
            url=_api_url(path),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return None, "Invalid response format from license server"
        return data, None
    except requests.exceptions.Timeout:
        return None, "Request timed out. Please check your internet connection."
    except requests.exceptions.ConnectionError:
        return None, "Connection error. Please check your internet connection."
    except requests.exceptions.HTTPError as e:
        status_code = getattr(e.response, "status_code", "unknown")
        try:
            error_payload = e.response.json() if e.response is not None else {}
        except Exception:
            error_payload = {}
        error_message = error_payload.get("error") or error_payload.get("message") or error_payload.get("detail")
        if error_message:
            return None, str(error_message)
        return None, f"HTTP error: {status_code}"
    except json.JSONDecodeError:
        return None, "Invalid JSON response from license server"
    except Exception as e:
        return None, f"Error contacting license server: {str(e)}"


def _legacy_validate(license_key: str, use_cache: bool = True) -> Tuple[bool, Optional[str]]:
    if not license_key:
        return False, "License key is empty"

    valid_keys, error = fetch_valid_keys_from_gist()

    if valid_keys is not None:
        is_valid = validate_license_key(license_key, valid_keys)
        store_license_key(license_key, valid_keys)

        if is_valid:
            return True, None
        return False, "Invalid license key"

    if use_cache:
        cached_keys = get_cached_valid_keys()
        if cached_keys:
            is_valid = validate_license_key(license_key, cached_keys)
            if is_valid:
                return True, None
            return False, f"Invalid license key (offline mode: {error})"

    return False, error or "Unable to validate license key"


def _legacy_check_subscription_state() -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    stored_key = get_stored_license_key()
    if not stored_key:
        return False, None, "License key is not stored"

    is_valid, error = _legacy_validate(stored_key, use_cache=True)
    if not is_valid:
        return False, None, error

    record = get_license_record()
    record.setdefault("license_key", stored_key)
    record.setdefault("validated_at", _iso_now())
    record["source"] = "legacy"
    save_license_record(record)
    return True, record, None


def _is_subscription_status_allowed(status: str) -> bool:
    return _normalize_status(status) in _ALLOWED_ACTIVE_STATUSES


def _status_error_message(status: str, response: Optional[Dict[str, Any]] = None) -> str:
    status = _normalize_status(status)
    if status == "seat_limit_reached":
        return "Your company has reached the seat limit for this subscription."
    if status == "expired":
        return "Your subscription has expired. Please renew to continue."
    if status == "canceled":
        return "Your subscription has been canceled. Please contact your administrator or support."
    if status == "revoked":
        return "This subscription has been revoked. Please contact support."
    if status == "past_due":
        return "Your subscription payment is past due."
    if response:
        message = response.get("message") or response.get("error") or response.get("detail")
        if message:
            return str(message)
    return "Subscription is not active"


def _within_offline_grace(record: Dict[str, Any]) -> bool:
    subscription = record.get("subscription") if isinstance(record.get("subscription"), dict) else {}
    grace_expires_at = _parse_datetime(subscription.get("offline_grace_expires_at") or record.get("offline_grace_expires_at"))
    if not grace_expires_at:
        return False
    return _utcnow() <= grace_expires_at


def _mark_offline_grace(record: Dict[str, Any]) -> Dict[str, Any]:
    subscription = dict(record.get("subscription") or {})
    subscription["status"] = "offline_grace"
    if not subscription.get("offline_grace_expires_at"):
        subscription["offline_grace_expires_at"] = (_utcnow() + timedelta(days=OFFLINE_GRACE_DAYS)).isoformat()
    subscription["last_synced_at"] = _iso_now()
    record["subscription"] = subscription
    record["validated_at"] = _iso_now()
    save_license_record(record)
    return record


def get_subscription_status() -> Dict[str, Any]:
    """Get the current subscription state from local storage."""
    record = get_license_record()
    subscription = record.get("subscription") if isinstance(record.get("subscription"), dict) else {}
    return subscription


def get_subscription_summary() -> Dict[str, Any]:
    """Return a merged view of the saved license record and subscription metadata."""
    record = get_license_record()
    return {
        "license_key": record.get("license_key"),
        "user_identifier": record.get("user_identifier"),
        "activation_token": record.get("activation_token"),
        "subscription": get_subscription_status(),
        "source": record.get("source"),
    }


def get_machine_fingerprint() -> str:
    """Expose the stable machine fingerprint used for seat tracking."""
    try:
        from core.machine_id import get_machine_fingerprint as _get_machine_fingerprint

        return _get_machine_fingerprint()
    except Exception:
        return "unknown-machine"


def get_subscription_status_from_record(record: Dict[str, Any]) -> str:
    subscription = record.get("subscription") if isinstance(record.get("subscription"), dict) else {}
    return _normalize_status(subscription.get("status"))


def activate_subscription(
    license_key: str,
    user_identifier: Optional[str],
    machine_fingerprint: Optional[str] = None,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Activate a monthly subscription for the given user and machine."""
    normalized_key = _normalize_license_key(license_key)
    user_identifier = (user_identifier or "").strip()
    machine_fingerprint = (machine_fingerprint or get_machine_fingerprint()).strip()

    if not normalized_key:
        return False, None, "License key is empty"

    if not user_identifier:
        # Fall back to the machine fingerprint as the activation identity.
        # The machine fingerprint already enforces per-device seat limits via
        # Lemon Squeezy's activation_limit, so a separate user identifier is
        # not required at activation time.
        user_identifier = machine_fingerprint

    if not LICENSE_API_BASE_URL:
        is_valid, error = _legacy_validate(normalized_key, use_cache=True)
        if not is_valid:
            return False, None, error

        record = get_license_record()
        record["license_key"] = normalized_key
        record["validated_at"] = _iso_now()
        record["user_identifier"] = user_identifier
        record["machine_fingerprint"] = machine_fingerprint
        record["activation_token"] = None
        record["source"] = "legacy"
        record = _merge_subscription_state(
            record,
            {
                "status": "legacy",
                "expires_at": None,
                "seat_limit": None,
                "seats_used": None,
                "company_id": None,
                "user_id": None,
                "management_url": get_manage_url(),
                "renewal_url": get_buy_url(),
                "last_synced_at": _iso_now(),
                "offline_grace_expires_at": (_utcnow() + timedelta(days=OFFLINE_GRACE_DAYS)).isoformat(),
            },
        )
        save_license_record(record)
        return True, record, None

    payload = {
        "license_key": normalized_key,
        "user_identifier": user_identifier,
        "machine_fingerprint": machine_fingerprint,
        "platform": sys.platform,
        "app_version": APP_VERSION,
    }

    response, error = _request_json("POST", "/activate", payload)
    if response is None:
        return False, None, error

    record = _build_subscription_state(normalized_key, user_identifier, machine_fingerprint, response)
    status = get_subscription_status_from_record(record)

    if not _is_subscription_status_allowed(status):
        save_license_record(record)
        return False, record, _status_error_message(status, response)

    save_license_record(record)
    return True, record, None


def refresh_subscription_state() -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Refresh the current subscription state from the backend or offline cache."""
    record = get_license_record()
    license_key = record.get("license_key")
    if not isinstance(license_key, str) or not license_key.strip():
        return False, None, "License key is not stored"

    if not LICENSE_API_BASE_URL:
        return _legacy_check_subscription_state()

    activation_token = record.get("activation_token")
    if not activation_token:
        return False, None, "No activation token found. Please activate your subscription again."

    user_identifier = record.get("user_identifier") or os.environ.get("ECTOFORM_USER_IDENTIFIER", "").strip()
    machine_fingerprint = record.get("machine_fingerprint") or get_machine_fingerprint()

    payload = {
        "license_key": license_key,
        "activation_token": activation_token,
        "user_identifier": user_identifier,
        "machine_fingerprint": machine_fingerprint,
        "platform": sys.platform,
        "app_version": APP_VERSION,
    }

    response, error = _request_json("POST", "/validate", payload)
    if response is None:
        if _within_offline_grace(record):
            offline_record = _mark_offline_grace(record)
            return True, offline_record, None
        return False, None, error

    record = _build_subscription_state(license_key, user_identifier, machine_fingerprint, response, existing_record=record)
    status = get_subscription_status_from_record(record)
    save_license_record(record)

    if _is_subscription_status_allowed(status):
        return True, record, None

    return False, record, _status_error_message(status, response)


def check_license_validity(
    license_key: str,
    use_cache: bool = True,
    user_identifier: Optional[str] = None,
    machine_fingerprint: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Check if a license key or subscription activation is valid.

    When the subscription API is configured, this performs first-time activation.
    Otherwise it falls back to the legacy Gist flow.
    """
    if not license_key:
        return False, "License key is empty"

    if LICENSE_API_BASE_URL:
        is_valid, _, error = activate_subscription(license_key, user_identifier, machine_fingerprint)
        return is_valid, error

    return _legacy_validate(license_key, use_cache=use_cache)


def is_license_valid_stored() -> bool:
    """Check whether the stored license/subscription is currently valid."""
    stored_key = get_stored_license_key()
    if not stored_key:
        return False

    if LICENSE_API_BASE_URL:
        is_valid, _, _ = refresh_subscription_state()
        return is_valid

    is_valid, _ = check_license_validity(stored_key, use_cache=True)
    return is_valid


def is_subscription_expired() -> bool:
    """Return True when the stored subscription is expired or blocked."""
    subscription = get_subscription_status()
    status = get_subscription_status_from_record({"subscription": subscription})
    if status in _BLOCKED_STATUSES:
        return True

    expires_at = _parse_datetime(subscription.get("expires_at"))
    return bool(expires_at and _utcnow() > expires_at)


# For testing/development
if __name__ == "__main__":
    print("License Validator Module")
    print(f"Config directory: {get_config_directory()}")
    print(f"Storage path: {get_license_storage_path()}")
    print(f"License API URL: {LICENSE_API_BASE_URL or '[not configured]'}")

    stored_key = get_stored_license_key()
    print(f"Stored key: {stored_key}")

    if stored_key:
        is_valid, error = check_license_validity(stored_key)
        print(f"Valid: {is_valid}, Error: {error}")
