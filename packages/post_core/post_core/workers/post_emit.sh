post_emit() {
  local kind="$1"; shift
  python3 - "$kind" "$@" <<'PYEOF'
import json, sys
kind = sys.argv[1]
data = {"kind": kind}
for arg in sys.argv[2:]:
    k, _, v = arg.partition("=")
    data[k] = v
print("##POST " + json.dumps(data), flush=True)
PYEOF
}
