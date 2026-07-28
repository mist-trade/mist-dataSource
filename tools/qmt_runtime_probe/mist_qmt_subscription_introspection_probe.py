# coding:gbk
"""One-shot, read-only QMT subscription API introspection.

Paste this whole file into a temporary QMT project. It never invokes a native
market-data or subscription method. The only side effect is writing one
sanitized JSON evidence file and printing the same evidence between markers.
"""

import hashlib
import inspect
import io
import json
import os
import re
import sys
import time
from contextlib import redirect_stdout
from typing import Any, Dict, List

OUTPUT_PATH = r"F:\quant\qmt\mist-qmt-subscription-introspection.json"
TEXT_LIMIT = 8192
REQUIRED_METHODS = (
    "subscribe_quote",
    "subscribe_whole_quote",
    "unsubscribe_quote",
    "get_market_data_ex",
)

# Optional operator-supplied metadata. Keep "unknown" when QMT does not expose it.
OPERATOR_QMT_BUILD = "unknown"
OPERATOR_TERMINAL_BUILD = "unknown"
OPERATOR_STRATEGY_RUNTIME_BUILD = "unknown"
OPERATOR_PERMISSION_TIER = "unknown"
OPERATOR_PROJECT_IDENTITY = "unknown"


def init(ContextInfo: Any) -> None:
    run_probe(ContextInfo)


def handlebar(ContextInfo: Any) -> None:
    _ = ContextInfo


def run_probe(ContextInfo: Any) -> Dict[str, Any]:
    evidence = _build_evidence(ContextInfo)
    encoded = json.dumps(evidence, sort_keys=True, indent=2)
    output_status = _write_output(encoded)
    print("MIST_QMT_SUBSCRIPTION_INTROSPECTION_BEGIN")
    print(encoded)
    print("MIST_QMT_SUBSCRIPTION_INTROSPECTION_END")
    print(
        "MIST_QMT_SUBSCRIPTION_INTROSPECTION_OUTPUT="
        + json.dumps(output_status, sort_keys=True)
    )
    return evidence


def _build_evidence(ContextInfo: Any) -> Dict[str, Any]:
    directory_names = []  # type: List[str]
    directory_error = ""
    try:
        directory_names = sorted(str(name) for name in dir(ContextInfo))
    except Exception as exc:
        directory_error = _error_text(exc)

    subscription_names = [
        name for name in directory_names if name.lower().startswith("subscribe")
    ]
    candidate_aliases = [
        name
        for name in subscription_names
        if "all" in name.lower() or "whole" in name.lower()
    ]
    method_names = []  # type: List[str]
    for name in list(REQUIRED_METHODS) + candidate_aliases:
        if name not in method_names:
            method_names.append(name)

    methods = {}  # type: Dict[str, Any]
    for name in method_names:
        methods[name] = _introspect_attribute(
            ContextInfo,
            name,
            name in directory_names,
        )

    return {
        "schemaVersion": 1,
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "probe": "mist_qmt_subscription_introspection_probe",
        "readOnly": True,
        "nativeMethodsInvoked": [],
        "mutationExecuted": False,
        "runtime": {
            "pythonVersion": _sanitize_text(sys.version),
            "pythonImplementation": _python_implementation(),
            "platform": _sanitize_text(sys.platform),
            "contextType": _sanitize_text(type(ContextInfo).__name__),
            "contextModule": _sanitize_text(type(ContextInfo).__module__),
        },
        "operatorMetadata": {
            "qmtBuild": OPERATOR_QMT_BUILD,
            "terminalBuild": OPERATOR_TERMINAL_BUILD,
            "strategyRuntimeBuild": OPERATOR_STRATEGY_RUNTIME_BUILD,
            "permissionTier": OPERATOR_PERMISSION_TIER,
            "projectIdentity": OPERATOR_PROJECT_IDENTITY,
        },
        "subscriptionApiIntrospection": {
            "dir": {
                "ok": not directory_error,
                "subscriptionNames": subscription_names,
                "error": directory_error,
            },
            "requiredMethods": list(REQUIRED_METHODS),
            "candidateAliases": candidate_aliases,
            "methods": methods,
        },
        "limitations": {
            "methodAvailabilityOnly": True,
            "returnValuesProven": False,
            "callbackBehaviorProven": False,
            "permissionValuesAreOperatorSupplied": True,
            "unknownMeansPlatformDidNotExposeOrOperatorCouldNotConfirm": True,
        },
    }


def _python_implementation() -> str:
    implementation = getattr(sys, "implementation", None)
    name = getattr(implementation, "name", None)
    return _sanitize_text(name if name is not None else "unknown")


def _introspect_attribute(target: Any, name: str, listed_in_dir: bool) -> Dict[str, Any]:
    try:
        value = getattr(target, name)
    except Exception as exc:
        return {
            "listedInDir": listed_in_dir,
            "getattr": {
                "ok": False,
                "found": False,
                "callable": False,
                "type": "",
                "error": _error_text(exc),
            },
            "__doc__": {"status": "unknown", "value": "", "error": "getattr failed"},
            "help": {"status": "unknown", "value": "", "error": "getattr failed"},
            "signature": {"status": "unknown", "value": "", "error": "getattr failed"},
        }

    return {
        "listedInDir": listed_in_dir,
        "getattr": {
            "ok": True,
            "found": True,
            "callable": callable(value),
            "type": _sanitize_text(type(value).__name__),
            "error": "",
        },
        "__doc__": _introspect_doc(value),
        "help": _introspect_help(value),
        "signature": _introspect_signature(value),
    }


def _introspect_doc(value: Any) -> Dict[str, str]:
    try:
        doc = getattr(value, "__doc__", None)
        if doc is None:
            return {"status": "missing", "value": "", "error": ""}
        return {"status": "known", "value": _bounded_text(doc), "error": ""}
    except Exception as exc:
        return {"status": "unknown", "value": "", "error": _error_text(exc)}


def _introspect_help(value: Any) -> Dict[str, str]:
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            help(value)
        return {"status": "known", "value": _bounded_text(output.getvalue()), "error": ""}
    except Exception as exc:
        return {
            "status": "unknown",
            "value": _bounded_text(output.getvalue()),
            "error": _error_text(exc),
        }


def _introspect_signature(value: Any) -> Dict[str, str]:
    try:
        return {
            "status": "known",
            "value": _bounded_text(inspect.signature(value)),
            "error": "",
        }
    except Exception as exc:
        return {"status": "unknown", "value": "", "error": _error_text(exc)}


def _bounded_text(value: Any) -> str:
    text = _sanitize_text(value)
    if len(text) <= TEXT_LIMIT:
        return text
    return text[:TEXT_LIMIT] + "...[truncated]"


def _sanitize_text(value: Any) -> str:
    text = str(value)
    text = re.sub(
        r"(?i)[A-Z]:\\Users\\[^\\\s\"']+",
        r"<USER_PROFILE>",
        text,
    )
    text = re.sub(
        r"(?i)(leaseToken[\"'\s:=]+)[^,\s}\"']+",
        r"\1<REDACTED>",
        text,
    )
    text = re.sub(
        r"(?i)(authorization[\"'\s:=]+bearer\s+)[^,\s}\"']+",
        r"\1<REDACTED>",
        text,
    )
    return text


def _error_text(exc: Exception) -> str:
    return type(exc).__name__ + ": " + _bounded_text(exc)


def _write_output(encoded: str) -> Dict[str, Any]:
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    try:
        output_dir = os.path.dirname(OUTPUT_PATH)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as output:
            output.write(encoded)
            output.write("\n")
        return {
            "ok": True,
            "path": OUTPUT_PATH,
            "contentSha256": digest,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "path": OUTPUT_PATH,
            "contentSha256": digest,
            "error": _error_text(exc),
        }
