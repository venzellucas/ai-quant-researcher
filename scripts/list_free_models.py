"""List the free models currently on OpenRouter, flagging likely stealth/alpha ones."""

import json
import urllib.request

with urllib.request.urlopen("https://openrouter.ai/api/v1/models") as r:
    data = json.load(r)["data"]

free = [
    m["id"]
    for m in data
    if float(m.get("pricing", {}).get("prompt", 1)) == 0
    and float(m.get("pricing", {}).get("completion", 1)) == 0
]

for mid in sorted(free):
    print(mid + ("   <-- stealth/alpha?" if "alpha" in mid.lower() else ""))
print(f"\n{len(free)} free models")
