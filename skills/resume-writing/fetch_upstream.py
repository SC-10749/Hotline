import json, hashlib, re, time, urllib.request, pathlib, datetime

REPO = "paramchoudhary/ResumeSkills"
BRANCH = "main"
BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/skills/"
FILES = {
    "resume-bullet-writer": "bullet-writer.md",
    "tech-resume-optimizer": "tech-resume-optimizer.md",
    "resume-ats-optimizer": "ats-optimizer.md",
    "resume-quantifier": "quantifier.md",
}
out_dir = pathlib.Path(r"F:\Hotline\skills\resume-writing\references")
out_dir.mkdir(parents=True, exist_ok=True)

def get(url, tries=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hotline-agent-doc-fetch"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2 + i * 3)
    raise last

meta = {"repo": f"https://github.com/{REPO}", "branch": BRANCH,
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"), "files": {}}
for name, fname in FILES.items():
    raw = get(BASE + name + "/SKILL.md")
    (out_dir / fname).write_bytes(raw)
    meta["files"][name] = {"path": f"references/{fname}", "url": BASE + name + "/SKILL.md",
                            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    print("saved", fname, len(raw))

try:
    html = get(f"https://github.com/{REPO}").decode("utf-8", "ignore")
    m = re.search(r'<strong>([\d.,]+k?)</strong>\s*stars', html)
    meta["stars"] = m.group(1) if m else None
except Exception as e:
    meta["stars"] = None
    meta["stars_error"] = str(e)
print("stars:", meta.get("stars"))
pathlib.Path(r"F:\Hotline\skills\resume-writing\PROVENANCE.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")