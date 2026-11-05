"""Query the JLCPCB assembly parts library for candidate components."""
import json
import sys
import urllib.request

API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def search(keyword, size=6):
    body = json.dumps({"keyword": keyword, "currentPage": 1, "pageSize": size}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["data"]["componentPageInfo"]["list"] or []


if __name__ == "__main__":
    for kw in sys.argv[1:]:
        print(f"=== {kw}")
        for c in search(kw):
            print(
                f"  {c.get('componentCode')}\t{c.get('componentLibraryType')}\tstock={c.get('stockCount')}\t"
                f"{c.get('componentModelEn')}\t{c.get('componentSpecificationEn')}\t{c.get('describe', '')[:70]}"
            )
