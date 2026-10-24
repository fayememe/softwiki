import argparse
import sys
import time

import requests
import yaml

REFUSAL_PATTERNS = [
    "out of scope",
    "reject",
    "don't have information",
    "do not have information",
    "insufficient evidence",
    "not enough evidence",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:6200")
    parser.add_argument("--file", default="tests/acceptance/golden_questions.yaml")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    with open(args.file, encoding="utf-8") as f:
        items = yaml.safe_load(f).get("questions", [])

    passed = 0
    for item in items:
        payload = {"question": item["question"]}
        if item.get("workflow"):
            payload["workflow"] = item["workflow"]

        started = time.time()
        reasons = []
        sources = []
        try:
            response = requests.post(
                args.api.rstrip("/") + "/api/ask", json=payload, timeout=args.timeout
            )
            latency = time.time() - started
            if not response.ok:
                reasons.append(f"HTTP {response.status_code}")
                answer = ""
            else:
                body = response.json()
                answer = body.get("answer", "") or ""
                sources = body.get("sources", []) or []

                if item.get("expect_refusal"):
                    lowered = answer.lower()
                    if not any(pattern in lowered for pattern in REFUSAL_PATTERNS):
                        reasons.append("expected refusal")
                else:
                    if not answer.strip():
                        reasons.append("empty answer")
                    for keyword in item.get("expect_keywords", []):
                        if keyword.lower() not in answer.lower():
                            reasons.append(f"missing keyword: {keyword}")
                    if item.get("require_pages") and not any(
                        source.get("page_start") is not None for source in sources
                    ):
                        reasons.append("no page citations")
                    if not sources:
                        reasons.append("no sources")
        except Exception as exc:
            latency = time.time() - started
            answer = ""
            reasons.append(f"exception: {exc}")

        ok = not reasons
        passed += int(ok)
        status = "PASS" if ok else "FAIL"
        print(
            f"[{status}] {item['id']} ({latency:.1f}s, {len(sources)} sources) "
            f"{'; '.join(reasons)}"
        )

    total = len(items)
    print(f"summary: {passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
