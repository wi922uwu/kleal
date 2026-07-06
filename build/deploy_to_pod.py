# -*- coding: utf-8 -*-
# Generate a remote bash script that reconstructs llm_demo_local.py on the pod as
# /root/llm_demo_app.py via gzip+base64 chunks (RunPod proxy SSH is PTY-only, no scp),
# verifies sha256, and restarts the demo on :7070. Pipe the script to `ssh -tt`.
import gzip, base64, hashlib
fp = r"C:\Projects\.dating\llm_demo_local.py"
data = open(fp, "rb").read()
sha = hashlib.sha256(data).hexdigest()
b64 = base64.b64encode(gzip.compress(data, 9)).decode("ascii")
CH = 1800
chunks = [b64[i:i+CH] for i in range(0, len(b64), CH)]

L = ["stty -echo 2>/dev/null", ": > /tmp/app.b64.gz"]
for c in chunks:
    L.append("printf '%%s' '%s' >> /tmp/app.b64.gz" % c)
L += [
    "base64 -d /tmp/app.b64.gz | gunzip > /root/llm_demo_app.py.new",
    "echo '===SHA==='",
    'GOT=$(sha256sum /root/llm_demo_app.py.new | cut -d" " -f1)',
    'echo "got=$GOT"; echo "exp=%s"' % sha,
    'if [ "$GOT" = "%s" ]; then' % sha,
    '  python3 -c "import ast,sys; ast.parse(open(chr(47).join([\'\',\'root\',\'llm_demo_app.py.new\'])).read())" && echo PARSE_OK || echo PARSE_FAIL',
    '  mv /root/llm_demo_app.py.new /root/llm_demo_app.py',
    '  pkill -9 -f llm_demo_app.py 2>/dev/null; sleep 2',
    '  DEMO_PORT=7070 nohup setsid python3 -u /root/llm_demo_app.py > /root/demo.log 2>&1 < /dev/null &',
    '  sleep 5',
    "  echo '===DEMOLOG==='; tail -n 5 /root/demo.log",
    "  echo '===APIMODELS==='; curl -s -m 6 localhost:7070/api/models | grep -o '\"id\":\"[^\"]*\"' | tr '\\n' ' '",
    '  echo',
    'else echo SHA_MISMATCH; fi',
    "echo '===END==='",
    "exit",
]
out = r"C:\Projects\.dating\build\_deploy_remote.sh"
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("file bytes:", len(data), "| gz+b64 len:", len(b64), "| chunks:", len(chunks), "| sha:", sha)
print("script:", out, "| lines:", len(L))
