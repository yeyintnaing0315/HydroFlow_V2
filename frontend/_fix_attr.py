from pathlib import Path
p = Path(r"D:\Ai_Project\HydroFlow_V2\frontend\src\App.tsx")
t = p.read_text(encoding="utf-8")
start = t.find("attribution=")
end = t.find("\n", start)
old = t[start:end]
if "Tiles" not in old:
    raise SystemExit("unexpected line: " + old)
new = 'attribution="&copy; Esri"'
t = t[:start] + new + t[end:]
out = p.with_name("App.tsx.new")
out.write_text(t, encoding="utf-8", newline="\n")
out.replace(p)
print("updated", len(t))
