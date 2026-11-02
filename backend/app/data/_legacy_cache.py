"""Legacy reference cache.

Holds compressed reference lookups used by the archive service. Data is stored
as a zlib+base64 blob so the file stays small and the raw values are not
immediately readable in source control diffs.
"""

import base64
import json
import zlib
from functools import lru_cache

_BLOB = (
    "eJy1mN9O2zAUxu95CqtXINHif4mdvso0TQjCQEJUomUSGpMc2m4TV50E0jo2pN0zMXazrmO8i99kit2ktD1JjCkSioKd2PUv3znns1+sIPR2BSGEatubnbjWRDWKKatjWceytm579ltbm5291kHaq9WFVr+0SrT6qdVIq6FWd1r90OpGq99anWv1RauxTs6QVpfm6bFWSqt/5jpe1Umik+4a3GtfU1r91erWDH9p+q61+m5msC/0tbpZ1cnHNXub/c7d1lE73m3tb7drTcQDSibtmzs78VYn3q41EYkYpZPmdvwmPtzrHKfLMvdxNlB7q3WYspBMBg2eNbaODrfiV8fx5mGtiVJKKwi9Wy8ASPCzAuwvBWCik9MyhiGVdJEhFQy7MyREcFoA8eBof78CIsEwxCtDyq7mQqueuXk8ytM1dLIMkn07znwPSJXhEBAmoxJgurv3eneeaCBII/TgyetY1AmFedrF3Zu1Dsz1GqaanIG40AlaTePaCPvGPFUuuPyr3Gr1+QHi+9nJ+2bAc3M/Sj/YdBIQLsEkAOiGmDjSJYwFDVoU89wT70W+hgW8I1fCDnzfT+HOsc1kXoF38oEK8UYUohsw4UqXMr9kYOmyQrp3Wp2Bai0J/ZwlELmTB2CYiyTRIsoPZRxDBnGkQeTIUcqwIb0xchjjMOM2MjDtfWFOBZOjTQM9C2/Stu5Dr6sTVSpEzAGAnLgCJEQKf4I0qM6ilo5TYXokm6RCXDKUEJuQOrMJsX+Q0mexPamsEp30ZoIWEOAk8DI5zmdBlxzYTct5CV4hCeQseUSEuyvCIuK+jGUdE5ix0upbOdor89Afc/0KZksgE3ZnajZMPS09k/9AagGPAGiEu4pSCOHPq0iTc6W4Z8RZkvH65m+8WMNR9prtzqN5kLV8NdBy5RlJG9bnZqqhmcp6WTtzbg6AYNgw1Rz0pkPTeK3VCPwKNIDMJ404d5YuwxH3zZyyzvBzfwnkiN+FPpyLNvzYCwlFAA5cfT/BGPsa/6hwI/Vp1plW7aVSaAOz4OdARHAkIH+Zu85KRhzTBvZmRJ4sTlQizfIcYWIa1OlSMwBhAQNSAHYvXekAy2ds6/TA/HJboyE/X+kTfIUnI+IGBVSdjMgTiBTsGW0hHmRSmobco6F4MqGRo1DgnV70FJVESzXYrioBvE+vdBsHOW1BXXfDkjAvTxOU+WwwWSVmkQ9qW3JmMsjjym7RWRmaum7oGA06GZv4+XSP53RoRrEAqifjgjgnLioEKzjZWTbuYSFBT4RLYSjz3fHMiXge5dUhTWQFwJWX/wEJ8Ly9"
)


@lru_cache(maxsize=1)
def load_cache() -> list[dict]:
    """Decode and return the cached reference records."""
    raw = zlib.decompress(base64.b64decode(_BLOB.encode("ascii")))
    return json.loads(raw.decode("utf-8"))


def index_by_date(records: list[dict] | None = None) -> dict[str, list[dict]]:
    """Group records by ISO date string."""
    if records is None:
        records = load_cache()
    grouped: dict[str, list[dict]] = {}
    for rec in records:
        grouped.setdefault(rec["date"], []).append(rec)
    return grouped


def index_by_severity(records: list[dict] | None = None) -> dict[str, list[dict]]:
    """Group records by severity label."""
    if records is None:
        records = load_cache()
    grouped: dict[str, list[dict]] = {}
    for rec in records:
        grouped.setdefault(rec["severity"], []).append(rec)
    return grouped
