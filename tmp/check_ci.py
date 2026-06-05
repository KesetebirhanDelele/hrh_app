import json

with open("outputs/domain_lessons_option_b/GLOBAL_20260605_001507/output_llm.json", encoding="utf-8") as f:
    payload = json.load(f)

ci_keywords = (
    "consequence", "resulted in", "led to", "increased", "delayed",
    "burden", "cost", "workload", "quality", "access", "reduced",
    "overwhelm", "overwhelmed", "stress", "strain",
    "impact", "profound", "suffering", "harm", "patient safety",
    "outcomes", "compromised", "risk", "mortality", "morbidity",
)
ci_broad = ("workload", "access", "cost", "delay", "burden", "quality", "care", "patient", "community", "staff")

fails = []
for domain in payload.get("domains", []):
    for fa in domain.get("focus_areas", []):
        for item in fa.get("consequences_impacts", []):
            snippets = [cit.get("snippet", "") for cit in item.get("citations", [])]
            has_kw = any(kw in snip.lower() for snip in snippets for kw in ci_keywords)
            if not has_kw:
                stmt = item.get("statement", "").lower()
                stmt_has_kw = any(kw in stmt for kw in ci_keywords)
                snip_broad = any(kw in snip.lower() for snip in snippets for kw in ci_broad)
                if not (stmt_has_kw and snip_broad):
                    snippet_preview = snippets[0][:80] if snippets else "NO SNIPPET"
                    domain_id = domain["domain_id"]
                    fa_id = fa["focus_area_id"]
                    item_id = item["item_id"]
                    fails.append(f"{domain_id}/{fa_id}/{item_id}: {snippet_preview}")

print(f"{len(fails)} failing items:")
for f in fails:
    print(" ", f)
