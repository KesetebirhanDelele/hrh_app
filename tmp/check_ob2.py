import json

with open("outputs/domain_lessons_option_b/GLOBAL_20260605_001507/output_llm.json", encoding="utf-8") as f:
    payload = json.load(f)

ob_keywords = (
    "lack of", "lacking", "without", "absence of", "insufficient",
    "inadequate", "barrier", "constraint", "difficulty",
    "hurdle", "challenge", "shortage",
    "negligible", "gap", "low coverage", "not being",
    "not meet", "low rate", "unavailability",
    "weak", "poor", "limited",
    "unplanned",
    "delayed", "not paid",
    "very low", "is low",
    "hardship", "unsafe", "insecure",
    "restrictions", "not uniform",
    "non-health", "non-hep",
    "sporadic", "inefficien",
    "no house",
    "challeng",
)
stmt_keywords = (
    "lengthy", "time-intensive", "time-consuming", "resources", "requires", "resource-intensive",
    "constraint", "challeng", "hurdle", "difficult", "burdensome",
    "inefficien", "weak",
)

fails = []
for domain in payload.get("domains", []):
    for fa in domain.get("focus_areas", []):
        for item in fa.get("operational_barriers", []):
            snippets = [cit.get("snippet", "") for cit in item.get("citations", [])]
            has_kw = any(kw in snip.lower() for snip in snippets for kw in ob_keywords)
            if not has_kw:
                stmt = item.get("statement", "").lower()
                stmt_has_kw = any(kw in stmt for kw in stmt_keywords)
                if not stmt_has_kw:
                    snippet_preview = snippets[0][:80] if snippets else "NO SNIPPET"
                    domain_id = domain["domain_id"]
                    fa_id = fa["focus_area_id"]
                    item_id = item["item_id"]
                    stmt_preview = stmt[:60]
                    fails.append(f"{domain_id}/{fa_id}/{item_id}\n    snip: {snippet_preview}\n    stmt: {stmt_preview}")

print(f"{len(fails)} failing items after removing 'low ' and 'workload':")
for f in fails:
    print(" ", f)
