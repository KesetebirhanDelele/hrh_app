import json, sys

output_file = sys.argv[1] if len(sys.argv) > 1 else "outputs/domain_lessons_option_b/GLOBAL_20260605_005939/output_llm.json"

with open(output_file, encoding="utf-8") as f:
    payload = json.load(f)

ob_keywords = (
    "lack of", "lacking", "without", "absence of", "insufficient",
    "inadequate", "barrier", "constraint", "difficulty",
    "hurdle", "challenge", "shortage",
    "negligible", "gap", "low coverage", "not being",
    "not meet", "low rate", "unavailability",
    "weak", "poor", "limited",
    "unplanned",
    "not paid",
    "very low", "is low",
    "hardship", "unsafe", "insecure",
    "restrictions", "not uniform",
    "non-health", "non-hep",
    "sporadic", "inefficien",
    "no house",
    "challeng",
    "mismatch",
)
ob_stmt_keywords = (
    "lengthy", "time-intensive", "time-consuming", "resources", "requires", "resource-intensive",
    "constraint", "challeng", "hurdle", "difficult", "burdensome",
    "inefficien", "weak",
)
ci_keywords = (
    "consequence", "resulted in", "led to", "increased", "delayed",
    "burden", "cost", "workload", "quality", "access", "reduced",
    "overwhelm", "overwhelmed", "stress", "strain",
    "impact", "profound", "suffering", "harm", "patient safety",
    "outcomes", "compromised", "risk", "mortality", "morbidity",
    "absenteeism", "part-time", "closed",
)
ci_broad = ("workload", "access", "cost", "delay", "burden", "quality", "care", "patient", "community", "staff")

for domain in payload.get("domains", []):
    for fa in domain.get("focus_areas", []):
        domain_id = domain["domain_id"]
        fa_id = fa["focus_area_id"]

        for item in fa.get("operational_barriers", []):
            snippets = [cit.get("snippet", "") for cit in item.get("citations", [])]
            has_kw = any(kw in snip.lower() for snip in snippets for kw in ob_keywords)
            if not has_kw:
                stmt = item.get("statement", "").lower()
                if not any(kw in stmt for kw in ob_stmt_keywords):
                    print(f"OB FAIL {domain_id}/{fa_id}/{item['item_id']}")
                    for i, snip in enumerate(snippets):
                        print(f"  snip[{i}]: {snip}")
                    print(f"  stmt: {stmt}")
                    print()

        for item in fa.get("consequences_impacts", []):
            snippets = [cit.get("snippet", "") for cit in item.get("citations", [])]
            has_kw = any(kw in snip.lower() for snip in snippets for kw in ci_keywords)
            if not has_kw:
                stmt = item.get("statement", "").lower()
                stmt_has_kw = any(kw in stmt for kw in ci_keywords)
                snip_broad = any(kw in snip.lower() for snip in snippets for kw in ci_broad)
                if not (stmt_has_kw and snip_broad):
                    print(f"CI FAIL {domain_id}/{fa_id}/{item['item_id']}")
                    for i, snip in enumerate(snippets):
                        print(f"  snip[{i}]: {snip}")
                    print(f"  stmt: {stmt}")
                    print()
